"""Log redaction: make sure secrets can never leak into log files.

Installs a redacting formatter on the root logger's handlers (this covers the
final rendered text of every record, including tracebacks) plus scrubbing
excepthooks for uncaught exceptions printed to stderr.

Redacts:
  - values of env vars that look like secrets (TOKEN/SECRET/PASSWORD/API_KEY)
  - Telegram bot token shape: ``bot<digits>:<alphanumerics>``
  - generic ``token=`` / ``api_key=`` style query params in URLs
"""
import logging
import os
import re
import sys

_PLACEHOLDER = '[REDACTED]'

_BOT_TOKEN_RE = re.compile(r'bot\d{5,15}:[A-Za-z0-9_-]{20,}')
_GENERIC_SECRET_PARAM_RE = re.compile(
    r'(?i)(token|api[_-]?key|client[_-]?secret|password|secret)=([^&\s\'"<>]+)'
)

_secrets_cache = None


def _collect_secrets():
    secrets = []
    for name, value in os.environ.items():
        upper = name.upper()
        if any(tag in upper for tag in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY')):
            if value and len(value) >= 8:
                secrets.append(value)
    # Longest first so overlapping values don't leave fragments.
    secrets.sort(key=len, reverse=True)
    return secrets


def scrub_text(text):
    """Return *text* with every known secret replaced by [REDACTED]."""
    global _secrets_cache
    if _secrets_cache is None:
        _secrets_cache = _collect_secrets()
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return text
    for secret in _secrets_cache:
        if secret in text:
            text = text.replace(secret, _PLACEHOLDER)
    text = _BOT_TOKEN_RE.sub('bot' + _PLACEHOLDER, text)
    text = _GENERIC_SECRET_PARAM_RE.sub(r'\1=' + _PLACEHOLDER, text)
    return text


class RedactingFormatter(logging.Formatter):
    """A logging.Formatter that scrubs secrets from the rendered record."""

    def format(self, record):
        return scrub_text(super().format(record))


def install_secret_redaction():
    """Attach redaction to the root logger's handlers and stderr excepthooks.

    Safe to call once at process startup, right after logging.basicConfig.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        fmt = handler.formatter
        if isinstance(fmt, RedactingFormatter):
            continue
        try:
            fmt_str = fmt._style._fmt if fmt is not None else None
            datefmt = fmt.datefmt if fmt is not None else None
        except Exception:
            fmt_str, datefmt = None, None
        if fmt_str:
            handler.setFormatter(RedactingFormatter(fmt_str, datefmt=datefmt))
        else:
            handler.setFormatter(RedactingFormatter())

    def _scrubbing_excepthook(etype, value, tb):
        import traceback
        sys.__stderr__.write(
            scrub_text(''.join(traceback.format_exception(etype, value, tb))))

    sys.excepthook = _scrubbing_excepthook
    try:
        import threading

        def _thread_excepthook(args):
            _scrubbing_excepthook(args.exc_type, args.exc_value,
                                  args.exc_traceback)

        threading.excepthook = _thread_excepthook
    except Exception:
        pass
    return True
