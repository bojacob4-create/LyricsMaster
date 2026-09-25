"""Round 56: recommendation display-casing normalization.

Rule: all-lowercase / ALL-UPPERCASE source artifacts -> Title Case;
intentional mixed-case stylization untouched; apostrophe-safe; idempotent.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import normalize_display_case as ndc
from services.recommendation_service import (
    format_recommendations,
    _get_similar_songs_uncached,
)
import services.recommendation_service as rs

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}\n    got:  {got!r}\n    want: {want!r}")


print("== helper ==")
check("all-lower", ndc("hate that i made you love me"),
      "Hate That I Made You Love Me")
check("all-upper", ndc("NEED YOU NOW"), "Need You Now")
check("unicode upper", ndc("BEYONCÉ"), "Beyoncé")
check("apostrophe", ndc("don't stop believin'"), "Don't Stop Believin'")
check("curly apostrophe", ndc("don\u2019t stop"), "Don\u2019t Stop")
check("mixed-case untouched", ndc("Man I Need"), "Man I Need")
check("already title untouched", ndc("Love Story"), "Love Story")
check("stylized lower single", ndc("bad guy"), "Bad Guy")
check("with parens", ndc("love story (taylor's version)"),
      "Love Story (Taylor's Version)")
check("numbers", ndc("21 questions"), "21 Questions")
check("empty", ndc(""), "")
check("none", ndc(None), None)
check("non-string", ndc(123), 123)
check("no letters", ndc("..."), "...")
check("idempotent", ndc(ndc("hate that i made you love me")),
      "Hate That I Made You Love Me")

print("== format_recommendations with raw dicts ==")
raw = [
    {"artist": "ariana grande", "name": "hate that i made you love me"},
    {"artist": "LADY ANTEBELLUM", "name": "NEED YOU NOW"},
    {"artist": "Olivia Dean", "name": "Man I Need"},
]
out = format_recommendations(raw, "Taylor Swift - Love Story")
check("lower artist+title normalized",
      "🔥 Ariana Grande — Hate That I Made You Love Me" in out, True)
check("upper artist+title normalized",
      "✨ Lady Antebellum — Need You Now" in out, True)
check("mixed-case preserved", "💫 Olivia Dean — Man I Need" in out, True)

print("== pipeline normalizes merged recs ==")
orig_lastfm = rs._get_lastfm_recommendations
orig_apple = rs._get_apple_recommendations
orig_chart = rs._get_lastfm_chart_recommendations
orig_merge = rs._merge_recommendations
try:
    rs._get_lastfm_recommendations = lambda *a, **k: [
        {"artist": "ariana grande", "name": "hate that i made you love me"}]
    rs._get_apple_recommendations = lambda *a, **k: []
    rs._get_lastfm_chart_recommendations = lambda *a, **k: []
    rs._merge_recommendations = lambda lfm, ap, ch, limit=5: list(lfm)
    merged = _get_similar_songs_uncached("Taylor Swift", "Love Story",
                                        "romantic", limit=1)
    check("pipeline artist", merged[0]["artist"], "Ariana Grande")
    check("pipeline name", merged[0]["name"],
          "Hate That I Made You Love Me")
finally:
    rs._get_lastfm_recommendations = orig_lastfm
    rs._get_apple_recommendations = orig_apple
    rs._get_lastfm_chart_recommendations = orig_chart
    rs._merge_recommendations = orig_merge

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
