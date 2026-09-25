#!/usr/bin/env python3
"""Generate Telegram hand-test lists from round test files.

The user hand-tests every round in Telegram from a list the assistant writes.
This tool derives that list from the round's test file so nothing is missed
and the format stays consistent.

Workflow:
    1. Finish the round's test file, e.g. test_round40.py
    2. Scaffold a spec:  python tools/gen_telegram_tests.py 40 --scaffold
       (writes tools/telegram_tests/round40.yaml pre-filled from the checks)
    3. Fill in command / expect for each case in the YAML
       (mark pure unit checks unit_only: true)
    4. Render the Telegram-ready list:
           python tools/gen_telegram_tests.py 40

Without a YAML spec the tool prints a best-effort draft straight from the
test file (docstring + check names + section comments) with low-confidence
items flagged [review].
"""

import ast
import io
import os
import re
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_DIR = os.path.join(HERE, 'telegram_tests')

# ---------------------------------------------------------------------------
# Tiny YAML subset (mappings, lists, `|` block scalars, bools, ints, comments).
# Deliberately strict: 2-space indent, `key: value` / `key: |` / `key:` forms.
# ---------------------------------------------------------------------------

def parse_simple_yaml(text):
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        lines.append((indent, stripped))
    if not lines:
        return {}
    val, _ = _parse_block(lines, 0, -1)
    return val if isinstance(val, dict) else {}


def _parse_block(lines, idx, parent_indent):
    """Parse a mapping or list block; return (value, next_idx)."""
    # Decide block kind from first line.
    indent, content = lines[idx]
    if content.startswith('- ') or content == '-':
        return _parse_list(lines, idx, indent)
    mapping = {}
    i = idx
    while i < len(lines):
        indent, content = lines[i]
        if indent <= parent_indent:
            break
        if content.startswith('- '):
            break  # shouldn't happen inside a mapping at this level
        key, _, rest = content.partition(':')
        key = key.strip()
        rest = rest.strip()
        if rest == '|':
            i += 1
            buf = []
            while i < len(lines) and lines[i][0] > indent:
                buf.append(lines[i][1])
                i += 1
            # strip one level of extra indent is unnecessary: we kept raw
            # content lines; re-derive from original spacing below.
            mapping[key] = '\n'.join(buf).strip('\n')
            continue
        if rest:
            mapping[key] = _scalar(rest)
            i += 1
            continue
        # Nested block: could be a mapping or a list.
        if i + 1 < len(lines) and lines[i + 1][0] > indent:
            nxt_indent, nxt_content = lines[i + 1]
            if nxt_content.startswith('- ') or nxt_content == '-':
                val, i = _parse_list(lines, i + 1, nxt_indent)
            else:
                val, i = _parse_block(lines, i + 1, indent)
            mapping[key] = val
        else:
            mapping[key] = None
            i += 1
    return mapping, i


def _parse_list(lines, idx, list_indent):
    items = []
    i = idx
    while i < len(lines):
        indent, content = lines[i]
        if indent != list_indent or not (content.startswith('- ') or content == '-'):
            break
        item = content[1:].strip()
        if not item:
            # `-` alone: nested block follows.
            if i + 1 < len(lines) and lines[i + 1][0] > list_indent:
                val, i = _parse_block(lines, i + 1, list_indent)
                items.append(val)
            else:
                items.append(None)
                i += 1
            continue
        if ':' in item and not item.startswith(('"', "'")):
            # `- key: value` inline mapping start.
            key, _, rest = item.partition(':')
            mapping = {}
            rest = rest.strip()
            if rest == '|':
                i += 1
                buf = []
                while i < len(lines) and lines[i][0] > list_indent:
                    buf.append(lines[i][1])
                    i += 1
                mapping[key.strip()] = '\n'.join(buf).strip('\n')
            elif rest:
                mapping[key.strip()] = _scalar(rest)
                i += 1
            else:
                mapping[key.strip()] = None
                i += 1
            # Continuation lines of this mapping (deeper indent).
            while i < len(lines) and lines[i][0] > list_indent:
                sub_indent, sub_content = lines[i]
                # A new list item at our level ends the mapping.
                if sub_indent == list_indent:
                    break
                k2, _, r2 = sub_content.partition(':')
                k2, r2 = k2.strip(), r2.strip()
                if r2 == '|':
                    i += 1
                    buf = []
                    while i < len(lines) and lines[i][0] > sub_indent:
                        buf.append(lines[i][1])
                        i += 1
                    mapping[k2] = '\n'.join(buf).strip('\n')
                    continue
                if r2:
                    mapping[k2] = _scalar(r2)
                    i += 1
                elif i + 1 < len(lines) and lines[i + 1][0] > sub_indent:
                    val, i = _parse_block(lines, i + 1, sub_indent)
                    mapping[k2] = val
                else:
                    mapping[k2] = None
                    i += 1
            items.append(mapping)
            continue
        items.append(_scalar(item))
        i += 1
    return items, i


def _scalar(text):
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
        return t[1:-1]
    if t.lower() == 'true':
        return True
    if t.lower() == 'false':
        return False
    if re.fullmatch(r'-?\d+', t):
        return int(t)
    return t


# ---------------------------------------------------------------------------
# Test-file parsing (AST + section comments).
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(r'#\s*─{2,}\s*(.+?)\s*─*\s*$')
COMMAND_RE = re.compile(r'/[a-z][a-z0-9_]*')

# function-name keyword -> Telegram command, checked after literal /commands.
FUNC_TO_COMMAND = [
    ('top_by_genre', '/top'),
    ('resolve_genre_key', '/top'),
    ('trending', '/trending'),
    ('daily', '/daily'),
    ('quiz', '/quiz'),
    ('translate', '/translate'),
    ('newmusic', '/newmusic'),
    ('new_music', '/newmusic'),
    ('mood', '/mood'),
    ('random_song', '/random'),
    ('artist_info', '/artist'),
    ('download', '/download'),
    ('lyrics', '/lyrics'),
    ('duel', '/duel'),
    ('about', '/about'),
    ('subscribe', '/subscribe'),
]

UNIT_HINTS = ('mock', 'fake', 'stub', 'cache', 'cached', 'import',
              'remnant', 'plumbing', 'unit_only', 'tmp', 'teardown')


def parse_test_file(path):
    with open(path, encoding='utf-8') as f:
        source = f.read()
    tree = ast.parse(source, path)
    docstring = ast.get_docstring(tree) or ''

    # Section comments: ((line, title), ...).
    sections = []
    try:
        toks = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in toks:
            if tok.type == tokenize.COMMENT:
                m = SECTION_RE.match(tok.string)
                if m:
                    sections.append((tok.start[0], m.group(1).strip()))
    except Exception:
        pass

    checks = []  # (lineno, name, section_title_or_None)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'check'
                and node.args):
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                name = first.value
            elif isinstance(first, ast.JoinedStr):
                # f-string name: keep the template with {placeholders}.
                name = re.sub(r"^f(['\"])", r'\1',
                              ast.unparse(first)).strip('\'"')
            else:
                continue
            sec = None
            for sline, stitle in sections:
                if sline < node.lineno:
                    sec = stitle
                else:
                    break
            checks.append((node.lineno, name, sec))
    checks.sort()
    return {'docstring': docstring, 'checks': checks}


def infer_command(name, section):
    hay = f'{name} {section or ""}'
    m = COMMAND_RE.search(name) or (COMMAND_RE.search(section or ''))
    if m:
        return m.group(0)
    low = hay.lower()
    for kw, cmd in FUNC_TO_COMMAND:
        if kw in low:
            return cmd
    return ''


def infer_expect(name):
    for sep in (' -> ', ' → ',):
        if sep in name:
            right = name.split(sep, 1)[1].strip()
            if right:
                return right[0].upper() + right[1:]
    if ': ' in name:
        left, right = name.split(': ', 1)
        if right.strip() and len(right) < 120:
            r = right.strip()
            return r[0].upper() + r[1:]
    h = name.replace('_', ' ').strip()
    return (h[0].upper() + h[1:]) if h else name


def looks_unit_only(name):
    low = name.lower()
    return any(h in low for h in UNIT_HINTS)


# ---------------------------------------------------------------------------
# Scaffold: YAML skeleton pre-filled from the test file.
# ---------------------------------------------------------------------------

def _yaml_str(text, indent):
    """Render a scalar, using a block scalar when multiline or tricky."""
    if '\n' in text or len(text) > 90 or text.strip().endswith(':'):
        pad = ' ' * (indent + 2)
        body = '\n'.join(pad + ln if ln.strip() else '' for ln in text.split('\n'))
        return '|\n' + body
    return text


def scaffold(round_num, parsed, out_path):
    doc = (parsed['docstring'] or '').strip()
    # Title: first non-empty docstring line, minus "Round-XX..." prefix noise.
    title = ''
    for ln in doc.splitlines():
        ln = ln.strip()
        if ln:
            title = re.sub(r'^[Rr]ound[-\s]*\d+[:\s]*', '', ln)
            title = re.sub(r'^tests?:?\s*', '', title, flags=re.I)
            break
    lines = [f'round: {round_num}']
    lines.append(f'title: {_yaml_str(title or f"Round {round_num}", 0)}')
    if doc:
        # Summary: docstring minus the title line.
        rest = '\n'.join(doc.splitlines()[1:]).strip()
        if rest:
            lines.append(f'summary: {_yaml_str(rest, 0)}')
    lines.append('tests:')
    for _, name, section in parsed['checks']:
        cmd = infer_command(name, section)
        exp = infer_expect(name)
        unit = looks_unit_only(name)
        lines.append(f'  - name: {_yaml_str(name, 4)}')
        if section:
            lines.append(f'    section: {_yaml_str(section, 6)}')
        lines.append(f'    command: {cmd}')
        lines.append(f'    expect: {_yaml_str(exp, 6)}')
        lines.append(f'    unit_only: {"true" if unit else "false"}')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return out_path


# ---------------------------------------------------------------------------
# Render: YAML spec -> Telegram-ready Markdown.
# ---------------------------------------------------------------------------

def render(spec):
    rnd = spec.get('round', '?')
    title = spec.get('title', '')
    out = [f'🧪 Telegram test list — Round {rnd}: {title}', '']
    summary = (spec.get('summary') or '').strip()
    if summary:
        # Keep the summary tight: first ~6 lines.
        s_lines = summary.splitlines()[:6]
        out.extend(s_lines + [''])
    n = 0
    unit_only_names = []
    last_section = None
    for t in spec.get('tests', []) or []:
        if t.get('unit_only'):
            unit_only_names.append(t.get('name', ''))
            continue
        n += 1
        section = (t.get('section') or '').strip()
        if section and section != last_section:
            out.append(f'— {section} —')
            last_section = section
        cmd = (t.get('command') or '').strip()
        name = (t.get('name') or '').strip()
        if cmd:
            out.append(f'{n}. Send `{cmd}`')
        else:
            out.append(f'{n}. {name}')
        for step in t.get('steps') or []:
            out.append(f'   • {step}')
        expect = (t.get('expect') or '').strip().replace('\n', '\n   ')
        if expect:
            out.append(f'   Expect: {expect}')
        note = (t.get('note') or '').strip().replace('\n', '\n   ')
        if note:
            out.append(f'   Note: {note}')
        out.append('')
    if unit_only_names:
        out.append('✅ Covered by automated suite (no Telegram step needed):')
        out.append('• ' + ' • '.join(unit_only_names))
        out.append('')
    return '\n'.join(out).rstrip() + '\n'


# ---------------------------------------------------------------------------
# Draft mode: no YAML yet — best-effort list straight from the test file.
# ---------------------------------------------------------------------------

def draft(parsed, round_num):
    out = [f'🧪 Telegram test list (DRAFT — no spec yet) — Round {round_num}', '']
    if parsed['docstring']:
        out.extend(parsed['docstring'].strip().splitlines()[:4] + [''])
    n = 0
    last_section = None
    for _, name, section in parsed['checks']:
        if section and section != last_section:
            out.append(f'— {section} —')
            last_section = section
        cmd = infer_command(name, section)
        exp = infer_expect(name)
        confident = bool(cmd) and not looks_unit_only(name)
        n += 1
        tag = '' if confident else ' [review]'
        if cmd:
            out.append(f'{n}. Send `{cmd}`{tag}')
        else:
            out.append(f'{n}. {name}{tag}')
        out.append(f'   Expect: {exp}')
        out.append('')
    out.append('Run with --scaffold to create an editable spec, fill in the')
    out.append('gaps, then re-render for the final list.')
    return '\n'.join(out) + '\n'


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def resolve_round_arg(arg):
    m = re.search(r'(\d+)', os.path.basename(arg))
    if not m:
        raise SystemExit(f'cannot find a round number in {arg!r}')
    return m.group(1)


def find_test_file(round_num):
    repo = os.path.dirname(HERE)
    cands = [f'test_round{round_num}.py']
    for c in cands:
        p = os.path.join(repo, c)
        if os.path.exists(p):
            return p
    raise SystemExit(f'no test file found for round {round_num}')


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__.strip())
        return 0
    arg = argv[0]
    want_scaffold = '--scaffold' in argv[1:]
    round_num = resolve_round_arg(arg)
    test_path = find_test_file(round_num)
    os.makedirs(SPEC_DIR, exist_ok=True)
    spec_path = os.path.join(SPEC_DIR, f'round{round_num}.yaml')

    if want_scaffold:
        parsed = parse_test_file(test_path)
        scaffold(round_num, parsed, spec_path)
        print(f'wrote {spec_path} — fill in command/expect, then render:')
        print(f'  python tools/gen_telegram_tests.py {round_num}')
        return 0

    if os.path.exists(spec_path):
        with open(spec_path, encoding='utf-8') as f:
            spec = parse_simple_yaml(f.read())
        sys.stdout.write(render(spec))
        return 0

    parsed = parse_test_file(test_path)
    sys.stdout.write(draft(parsed, round_num))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
