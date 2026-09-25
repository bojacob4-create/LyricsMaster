# tools/

## gen_telegram_tests.py — Telegram hand-test list generator

The user hand-tests every round in Telegram from a written test list.
This tool derives that list from the round's test file so no check is
missed and the format stays consistent.

```bash
# 1. scaffold a spec from the round's test file
python tools/gen_telegram_tests.py 40 --scaffold

# 2. fill in command / expect in tools/telegram_tests/round40.yaml
#    (mark pure unit checks unit_only: true)

# 3. render the Telegram-ready list
python tools/gen_telegram_tests.py 40
```

Without a spec file it prints a best-effort draft straight from the test
file (docstring + check names + section comments), flagging uncertain
items with `[review]`.

The spec format is a tiny strict YAML subset (mappings, lists, `|` block
scalars, booleans) — no PyYAML dependency. `test_tg_gen.py` covers the
parser, the test-file extraction, the heuristics, and the renderer.
