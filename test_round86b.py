"""Round 86b: share-card cache invalidation on template changes. Run: ../venv/bin/python test_round86b.py

Bug (found 2026-09-26 from the user's wild test): share cards are cached
on disk under a deterministic token (<token>.png) with no template
versioning, so after the round-86 visual polish the bot kept serving the
old-template render — logs showed "[sharecard] cache hit" for a card
cached hours before the deploy.

Fix: card_cache_path() now embeds TEMPLATE_VERSION in the file name.
Bumping the version retires every previously cached render; stale files
are simply never looked up again.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import services.share_card as sc

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")


# 1. The cache path carries the template version ...
token = "ab12cd34ef56"
p = sc.card_cache_path(token)
check("version in filename", os.path.basename(p),
      f"{token}_v{sc.TEMPLATE_VERSION}.png")

# 2. ... and a version bump changes the path (old files never hit again).
old_version = sc.TEMPLATE_VERSION
sc.TEMPLATE_VERSION = old_version + 1
try:
    p2 = sc.card_cache_path(token)
    check("bump changes path", p2 != p, True)
    check("bump reflected in filename", os.path.basename(p2),
          f"{token}_v{old_version + 1}.png")
finally:
    sc.TEMPLATE_VERSION = old_version

# 3. Same token + same version => same path (cache still works).
check("deterministic path", sc.card_cache_path(token), p)

# 4. Version is a positive int.
check("version sane",
      isinstance(sc.TEMPLATE_VERSION, int) and sc.TEMPLATE_VERSION >= 1, True)

# 5. Tokens stay deterministic (the whole point of the cache).
t1 = sc.get_share_token("Teddy Swims", "Lose Control")
t2 = sc.get_share_token("Teddy Swims", "Lose Control")
check("token deterministic", t1, t2)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
