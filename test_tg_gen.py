"""Tests for tools/gen_telegram_tests.py (the Telegram test-list generator)."""
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))
import gen_telegram_tests as g

PASS, FAIL = 0, 0
FAILURES = []


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)
    print(('  PASS ' if cond else '  FAIL ') + name)


# ── tiny YAML subset ──────────────────────────────────────────────────────

SAMPLE = textwrap.dedent('''\
    round: 40
    title: /top is 100% live
    summary: |
      Line one.
      Line two with "quotes": fine.
    tests:
      - name: kpop is fully live
        command: /top kpop
        expect: |
          7 songs, every one tagged "Charting now on Apple Music".
          Source line reads "Source: Apple Music Charts".
        note: Korea is home.
        unit_only: false
      - name: resolve pop
        unit_only: true
      - name: multi-command sweep
        command: /top pop
        steps:
          - Repeat for /top rap
          - Repeat for /top rock
        expect: 7 songs each time.
    ''')

spec = g.parse_simple_yaml(SAMPLE)
check('round parsed as int', spec['round'] == 40)
check('title kept', spec['title'] == '/top is 100% live')
check('block scalar summary', spec['summary'] == 'Line one.\nLine two with "quotes": fine.')
check('3 tests parsed', len(spec['tests']) == 3)
t0 = spec['tests'][0]
check('multiline expect kept', t0['expect'].startswith('7 songs, every one tagged "Charting now'))
check('bool false parsed', t0['unit_only'] is False)
check('unit_only true parsed', spec['tests'][1]['unit_only'] is True)
check('steps list parsed', spec['tests'][2]['steps'] == ['Repeat for /top rap', 'Repeat for /top rock'])
check('plain expect scalar', spec['tests'][2]['expect'] == '7 songs each time.')

# comments + blank lines are ignored
spec2 = g.parse_simple_yaml('# hello\n\nround: 7\n')
check('comments ignored', spec2 == {'round': 7})
check('empty yaml -> {}', g.parse_simple_yaml('') == {})

# ── test-file parsing ─────────────────────────────────────────────────────

SRC = textwrap.dedent('''\
    """Round-99 tests: the frobnicator round.

    Makes /frob live.
    """
    def check(name, cond):
        pass

    # ── resolution ──
    check("resolve frob", True)
    check(f"live smoke {_g}: all live", True)
    ''')
path = '/tmp/_tggen_sample_test.py'
with open(path, 'w') as f:
    f.write(SRC)
parsed = g.parse_test_file(path)
check('docstring extracted', 'frobnicator' in parsed['docstring'])
check('literal check found', any(n == 'resolve frob' for _, n, _ in parsed['checks']))
check('f-string check found', any(n == 'live smoke {_g}: all live' for _, n, _ in parsed['checks']))
check('section attached', any(s == 'resolution' for _, _, s in parsed['checks']))

# ── inference ─────────────────────────────────────────────────────────────

check('literal /cmd wins', g.infer_command('second /daily refused', 'daily game') == '/daily')
check('section /cmd used', g.infer_command('starts game', '/daily flow') == '/daily')
check('func keyword maps', g.infer_command('top songs listed', 'get_top_by_genre') == '/top')
check('no hint -> empty', g.infer_command('imports fine', 'sanity') == '')
check('arrow expect', g.infer_expect('resolve unknown -> None') == 'None')
check('colon expect', g.infer_expect('apple-full: 7 songs') == '7 songs')
check('unit hint detected', g.looks_unit_only('result cached'))
check('behavior not unit', not g.looks_unit_only('kpop is fully live'))

# ── render ────────────────────────────────────────────────────────────────

out = g.render(spec)
check('render header', out.startswith('🧪 Telegram test list — Round 40: /top is 100% live'))
check('render command', 'Send `/top kpop`' in out)
check('multiline expect indented',
      '   Source line reads "Source: Apple Music Charts".' in out)
check('steps rendered', '• Repeat for /top rap' in out)
check('unit-only footer', '✅ Covered by automated suite' in out and 'resolve pop' in out)

# ── draft mode (no spec) ──────────────────────────────────────────────────

d = g.draft(parsed, 99)
check('draft header', 'DRAFT' in d and 'Round 99' in d)
check('draft lists checks', 'resolve frob' in d and 'live smoke {_g}: all live' in d)

print(f'\n{ PASS} passed, {FAIL} failed')
if FAILURES:
    print('FAILURES:', FAILURES)
    sys.exit(1)
