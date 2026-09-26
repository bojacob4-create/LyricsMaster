"""Round 72 — /start & /help coverage parity (no missing commands).

Guards the round-71b lesson (a shipped command missing from a surface):
  1. every CommandHandler registered in bot.py is listed in /start
  2. every CommandHandler is listed in /help (except /start itself)
  3. BotCommand menu entries match CommandHandlers exactly (both directions)
  4. _KNOWN_COMMANDS covers every registered handler
  5. /start and /help share the same section headers in the same order
     (/help may append its "How to use" examples footer)

Pure source-scan, no network, no production state touched.
Run: python test_round72.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

passed, failed = 0, 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}")


bot_src = open("bot.py").read()
h_src = open("handlers.py").read()

handlers = sorted(set(re.findall(r'CommandHandler\("([a-z]+)"', bot_src)))
menu = sorted(set(re.findall(r'BotCommand\("([a-z]+)"', bot_src)))
_kc_start = h_src.find("_KNOWN_COMMANDS = [")
_kc_end = h_src.find("]", _kc_start)
known = re.findall(r"'([a-z]+)'", h_src[_kc_start:_kc_end])


def block(name):
    i = h_src.find(f"def {name}(")
    j = h_src.find("\ndef ", i + 10)
    return h_src[i:j]


start_b, help_b = block("start_command"), block("help_command")

# 1. /start lists everything
missing_start = [c for c in handlers if f"/{c}" not in start_b]
check(f"/start complete (missing={missing_start})", not missing_start)

# 2. /help lists everything except /start itself
missing_help = [c for c in handlers if c != "start" and f"/{c}" not in help_b]
check(f"/help complete (missing={missing_help})", not missing_help)

# 3. menu <-> handlers exact match
check(f"menu==handlers (menu-only={[c for c in menu if c not in handlers]}, "
      f"handler-only={[c for c in handlers if c not in menu]})",
      menu == handlers)

# 4. _KNOWN_COMMANDS coverage
missing_known = [c for c in handlers if c not in known]
check(f"_KNOWN_COMMANDS covers handlers (missing={missing_known})",
      not missing_known)

# 5. section parity
def sections(b):
    return re.findall(r"\*([^\*\n]{2,30})\*\\n", b)

ss, hs = sections(start_b), sections(help_b)
# /start ends with a "Try it now:" prompt footer, not a command section.
ss = [s for s in ss if s != "Try it now:"]
check(f"section parity (start={ss}, help={hs})",
      hs[:len(ss)] == ss and len(hs) in (len(ss), len(ss) + 1))

print(f"\nround72: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
