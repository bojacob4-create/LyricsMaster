"""Round 45: /extend reason de-noising + bare 'Extend' + fallback rewording.

Fix 1: per-song reasons no longer repeat the header vibe ("Fits your
Afrobeats • Relaxed vibe") — they carry only the distinctive pool note,
or nothing.
Fix 2: a message whose first line is exactly 'extend' (any case, no slash)
routes to /extend.
Fix 3: the low-confidence fallback no longer demands the 'Artist - Song'
format (the bot accepts natural queries).
"""
import sys
sys.path.insert(0, '.')

import handlers as h
from services import discovery_service as d
from services.nlp_router import low_confidence_message

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} :: {detail}")


# ── Fix 1: reasons ─────────────────────────────────────────────────────
_old = d.get_similar_songs
d.get_similar_songs = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
try:
    recs = d.get_extend_recs(
        [{"artist": "Tyla", "song": "Water"},
         {"artist": "Rema", "song": "Calm Down"},
         {"artist": "Ayra Starr", "song": "Rush"}], 5)
    check("reasons: 5 recs", len(recs) == 5, str(recs))
    check("reasons: no vibe repetition",
          all("Fits your" not in (r.get("reason") or "")
              and "Matches your" not in (r.get("reason") or "")
              for r in recs),
          str([r.get("reason") for r in recs]))
    # Notes survive verbatim where the pool has them.
    noted = {(e["artist"].lower(), e["song"].lower()): e.get("note")
             for e in d.GENRE_TOP_SONGS.get("afrobeats", []) if e.get("note")}
    for r in recs:
        k = (r["artist"].lower(), r["name"].lower())
        if k in noted:
            check(f"reasons: note kept for {r['name']}",
                  r["reason"] == noted[k], repr(r["reason"]))
finally:
    d.get_similar_songs = _old

# ── Fix 2: bare 'Extend' ───────────────────────────────────────────────
for text, want in [("Extend", True), ("extend", True), ("  EXTEND  ", True),
                   ("Extend\nTyla water\nRema calm down", True),
                   ("/extend", False), ("extend my playlist", False),
                   ("Pretend", False), ("Extended", False), ("", False),
                   ("please extend this", False)]:
    check(f"bare-extend: {text!r} -> {want}",
          h._is_bare_extend(text) == want)


class _Chat:
    def send_action(self, action=None):
        pass


class _Msg:
    def __init__(self, text):
        self.text = text
        self.chat = _Chat()
        self.replies = []

    def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return text


class _Update:
    def __init__(self, text):
        self.message = _Msg(text)
        self.effective_user = type("U", (), {"id": 999001})()


_old = d.get_similar_songs
d.get_similar_songs = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
try:
    u = _Update("Extend\nTyla water\nRema calm down\nAyra starr rush")
    h.extend_command(u, None)
    body = "\n".join(u.message.replies)
    check("extend_command: bare 'Extend' + songs -> results",
          "Based on your songs" in body, body[:160])
    check("extend_command: vibe label present",
          "Afrobeats" in body, body[:160])
    check("extend_command: no vibe repetition in reasons",
          "Fits your" not in body and "Matches your" not in body, body[:400])

    u2 = _Update("Extend")
    h.extend_command(u2, None)
    body2 = "\n".join(u2.message.replies)
    check("extend_command: bare 'Extend' alone -> song prompt",
          "Finish My Playlist" in body2, body2[:160])
finally:
    d.get_similar_songs = _old

# ── Fix 3: fallback rewording ──────────────────────────────────────────
msg = low_confidence_message()
check("fallback: no 'use the format' demand",
      "use the format" not in msg.lower(), msg)
check("fallback: natural example shown",
      "The Weeknd Blinding Lights" in msg, msg)
check("fallback: still offers commands",
      "/lyrics" in msg and "/recommend" in msg, msg)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
