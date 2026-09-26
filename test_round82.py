"""Round-82 tests: pin the OpenAI translation fallback to Modern Standard
Arabic.

Production case (2026-09-26): the Arabic translation of "KAROL G,
Judeline, & rusowsky - BbY WOW" came out in Egyptian dialect
("إزاي", "مش", "عايز"). Logs showed Google Translate's endpoint was
rate-limiting the bot (breaker active), so the translation went through
the OpenAI fallback — whose prompt said only "translate to Arabic".
" Arabic" is ambiguous to the model (MSA / Egyptian / Levantine /
Gulf), and with no anchor it drifted into Egyptian, the most-represented
Arabic variety in training data.

Fix: _openai_system_prompt() pins "Modern Standard Arabic (فصحى) —
never a regional dialect" when dest_lang == 'ar', so the fallback
agrees with the Google path (which always returns MSA). Other
languages' prompts are byte-identical to before.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.translator_service import _openai_system_prompt

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


ar = _openai_system_prompt('ar')
check("arabic prompt pins Modern Standard Arabic",
      "Modern Standard Arabic" in ar, ar)
check("arabic prompt names فصحى", "فصحى" in ar, ar)
check("arabic prompt forbids regional dialects",
      "never a regional dialect" in ar, ar)
check("arabic prompt keeps the base instructions",
      "Preserve line breaks" in ar and "Output ONLY the translation" in ar,
      ar)

es = _openai_system_prompt('es')
check("spanish prompt has no dialect pin",
      "Modern Standard Arabic" not in es and "dialect" not in es, es)
check("spanish prompt still targets Spanish",
      "Spanish" in es and "Preserve line breaks" in es, es)

fr = _openai_system_prompt('fr')
check("french prompt unchanged in spirit",
      "French" in fr and "dialect" not in fr, fr)

print(f"\nround82: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
