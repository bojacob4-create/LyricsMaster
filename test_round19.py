"""Round-19 tests: mood mix strips classical catalog noise.

iTunes classical feeds return full catalog entries ('Beethoven: Sonata
No. 14 "Moonlight" in C-Sharp Minor, Op. 27 No 2: I. Adagio sostenuto I')
and triple artist credits ('Chloe Flower, Academy of St Martin in the
Fields & Jessica Cottis'). Cleaned once in _send_mood_mix, the display
lines, button callbacks and card-context keys all use the clean names —
so the song card resolves the right song as a side effect.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers as h

passed, failed = 0, 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"ok    {name}")
    else:
        failed += 1
        print(f"FAIL  {name} :: {detail}")

ca, ct = h._clean_mix_artist, h._clean_mix_title

# ── 1. artist cleaning ───────────────────────────────────────────────────
check("triple credit -> primary",
      ca("Chloe Flower, Academy of St Martin in the Fields & Jessica Cottis")
      == "Chloe Flower")
check("ensemble & director -> ensemble",
      ca("La Serenissima & Adrian Chandler") == "La Serenissima")
check("orchestra & soloist -> orchestra",
      ca("Max Richter Orchestra & Lorenz Dangel") == "Max Richter Orchestra")
check("composer & pianist -> composer",
      ca("Ludwig van Beethoven & Mats Widlund") == "Ludwig van Beethoven")
check("short duo act untouched", ca("Simon & Garfunkel") == "Simon & Garfunkel")
check("plain artist untouched", ca("Tyla") == "Tyla")
check("single name untouched", ca("Anna Lapwood") == "Anna Lapwood")

# ── 2. title cleaning ────────────────────────────────────────────────────
check("quoted nickname + work type",
      ct("Ludwig van Beethoven",
         'Beethoven: Sonata No. 14 "Moonlight" in C-Sharp Minor, Op. 27 No 2: '
         'I. Adagio sostenuto I') == "Moonlight Sonata")
check("opus + movement stripped",
      ct("La Serenissima",
         "Sonata No. 15 for Violin, Cello & Continuo in G Minor, Op. 6: "
         "V. Giga. Allegro")
      == "Sonata No. 15 for Violin, Cello & Continuo in G Minor")
check("leading movement + parenthetical stripped",
      ct("Anna Lapwood",
         "I. Prologue: One Ring to Rule Them All "
         "(The Lord of the Rings Organ Symphony)")
      == "One Ring to Rule Them All")
check("plain titles untouched",
      ct("Chloe Flower", "Song for Snow") == "Song for Snow")
check("plain titles untouched 2",
      ct("Max Richter Orchestra", "On the Nature of Daylight")
      == "On the Nature of Daylight")
check("non-classical title untouched",
      ct("Tyla", "Water") == "Water")

# ── 3. end-to-end: mix text + button payloads use clean names ────────────
captured = {}

class FakeChat:
    def send_action(self, action=None):
        pass

class FakeMessage:
    chat = FakeChat()
    def reply_text(self, text, **kw):
        captured["text"] = text
        captured["markup"] = kw.get("reply_markup")

class FakeUpdate:
    message = FakeMessage()

noisy = [
    {"artist": "Chloe Flower, Academy of St Martin in the Fields & Jessica Cottis",
     "name": "Song for Snow", "source": "fresh"},
    {"artist": "Ludwig van Beethoven & Mats Widlund",
     "name": 'Beethoven: Sonata No. 14 "Moonlight" in C-Sharp Minor, Op. 27 No 2: I. Adagio sostenuto I',
     "source": "fresh"},
]

with patch.object(h, "get_mood_mix", return_value=noisy), \
     patch.object(h, "_fetch_mix_durations", return_value=["2:14", "1:07"]), \
     patch.object(h, "log_interaction", return_value=None):
    h._send_mood_mix(FakeUpdate(), 123, "focus")

text = captured.get("text", "")
check("line 1 clean with duration",
      "1. 🆕 Chloe Flower — Song for Snow ⏱️ 2:14" in text, text[:160])
check("line 2 nickname extracted",
      '2. 🆕 Ludwig van Beethoven — Moonlight Sonata ⏱️ 1:07' in text,
      text[160:320])
check("no opus/catalog noise left",
      "Op." not in text and "Adagio" not in text and "Academy of St" not in text)

# button callbacks carry the clean query (this is what the song card gets)
markup = captured.get("markup")
payloads = []
if markup:
    for row in markup.inline_keyboard:
        for btn in row:
            payloads.append(btn.callback_data)
check("buttons carry clean callback data",
      any("Moonlight Sonata" in (p or "") for p in payloads)
      and not any("Op. 27" in (p or "") for p in payloads),
      repr(payloads[:2]))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
