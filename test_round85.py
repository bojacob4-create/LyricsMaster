"""Round-85 tests: title-claimed officialness requires channel corroboration.

Production case (2026-09-26): the song card for 'Tate McRae - TRYING ON
SHOES' linked a re-upload titled '(Official Music Video)' by the
third-party channel TITFOR4TAT, while the artist's own channel hosts the
genuine '(Lyric Video)'. Root cause: is_official was an OR — title
markers ('official music video' in the title) counted the same as an
authoritative channel, and the round-81 'official wins' override then
leapfrogged the impersonator above the genuine upload. Any channel can
type '(Official Music Video)' into a title.

Fix: _channel_corroborates_official() (shared by scorer + kind
classifier, round-79 principle) — a title's officialness claim only
counts when the uploader is VEVO/'official'-suffixed or the channel
name matches the artist (incl. 'Artist - Topic' channels). Scorer
official-text bonuses and the kind classifier both require it; the
VEVO/official-channel-alone branch is unchanged.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from services import youtube_service as yt

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")


ARTIST, SONG = "Tate McRae", "Trying On Shoes"
FAKE_TITLE = "Tate McRae - Trying On Shoes (Official Music Video)"
FAKE = {'id': 'FAKEID123', 'title': FAKE_TITLE, 'channel': 'TITFOR4TAT'}
REAL_LYRIC = {'id': 'REALID456', 'title': "Tate McRae - TRYING ON SHOES (Lyric Video)",
              'channel': 'Tate McRae'}

# ── Corroboration helper ─────────────────────────────────────────────
check("r85: random re-uploader does not corroborate",
      yt._channel_corroborates_official("TITFOR4TAT", ARTIST) is False)
check("r85: artist's own channel corroborates",
      yt._channel_corroborates_official("Tate McRae", ARTIST) is True)
check("r85: VEVO corroborates",
      yt._channel_corroborates_official("TateMcRaeVEVO", ARTIST) is True)
check("r85: 'Artist - Topic' channel corroborates",
      yt._channel_corroborates_official("Tate McRae - Topic", ARTIST) is True)
check("r85: unrelated label channel does not corroborate",
      yt._channel_corroborates_official("Some Records", ARTIST) is False)
check("r85: empty channel does not corroborate",
      yt._channel_corroborates_official("", ARTIST) is False)
# Round-85b: spaceless official channel ('RodWave' for artist 'Rod Wave')
check("r85b: spaceless artist channel corroborates",
      yt._channel_corroborates_official("RodWave", "Rod Wave") is True)
check("r85b: spaceless fan channel does NOT corroborate",
      yt._channel_corroborates_official("RodWaveFan", "Rod Wave") is False)

# ── Kind classifier ─────────────────────────────────────────────────
check("r85: fake-official classifies as 'other', not 'official'",
      yt._classify_video_kind(FAKE_TITLE, "TITFOR4TAT", ARTIST, SONG)['kind'] == 'other',
      str(yt._classify_video_kind(FAKE_TITLE, "TITFOR4TAT", ARTIST, SONG)))
check("r85: same title on artist channel stays 'official'",
      yt._classify_video_kind(FAKE_TITLE, "Tate McRae", ARTIST, SONG)['kind'] == 'official')
check("r85: VEVO plain title stays 'official' (channel-alone branch)",
      yt._classify_video_kind("Tate McRae - Trying On Shoes", "TateMcRaeVEVO",
                              ARTIST, SONG)['kind'] == 'official')
check("r85: genuine artist-channel lyric video is 'lyric'",
      yt._classify_video_kind(REAL_LYRIC['title'], "Tate McRae", ARTIST, SONG)['kind'] == 'lyric')

# ── Scorer: official-text bonus is gated ────────────────────────────
s_fake = yt._score_candidate(FAKE, ARTIST, SONG)
s_fake_plain = yt._score_candidate(
    {'id': 'x', 'title': "Tate McRae - Trying On Shoes", 'channel': 'TITFOR4TAT'},
    ARTIST, SONG)
check("r85: impersonator gets no official-text bonus (markers add nothing)",
      s_fake == s_fake_plain, f"{s_fake} vs {s_fake_plain}")
s_corroborated = yt._score_candidate(
    {'id': 'x', 'title': FAKE_TITLE, 'channel': 'Tate McRae'}, ARTIST, SONG)
s_corroborated_plain = yt._score_candidate(
    {'id': 'x', 'title': "Tate McRae - Trying On Shoes", 'channel': 'Tate McRae'},
    ARTIST, SONG)
check("r85: corroborated channel keeps the +25 official-text bonus",
      s_corroborated - s_corroborated_plain == 25,
      f"{s_corroborated} vs {s_corroborated_plain}")
s_lyric = yt._score_candidate(REAL_LYRIC, ARTIST, SONG)
check("r85: genuine lyric outscores the impersonator",
      s_lyric > s_fake, f"{s_lyric} vs {s_fake}")

# ── End-to-end pick: the 'official wins' override must not crown the fake
with patch.object(yt, '_fetch_candidates', return_value=[FAKE, REAL_LYRIC]):
    best, score, seen = yt._search_best(ARTIST, SONG, ['tate mcrae trying on shoes'])
check("r85: pick is the artist-channel lyric video, not the fake official",
      best is not None and best['id'] == 'REALID456',
      f"picked {best['id'] if best else None} score={score}")
check("r85: winner kind is honest 'lyric'",
      yt._classify_video_kind(best['title'], best['channel'], ARTIST, SONG)['kind'] == 'lyric')

# ── Round-85b production case: Rod Wave - Dope Girl ───────────────────
# Genuine '(Official Audio)' on the artist's spaceless channel 'RodWave'
# must beat '(Lyrics)' re-uploads from third-party channels.
RW_ARTIST, RW_SONG = "Rod Wave", "Dope Girl"
RW_GENUINE = {'id': 'g9Yo1sLnbjo',
              'title': 'Rod Wave - Dope Girl (Official Audio)',
              'channel': 'RodWave'}
RW_LYRIC_FAKE = {'id': '2-D1AauBSdo',
                 'title': 'Rod Wave - Dope Girl (Lyrics)',
                 'channel': 'Rap City'}
check("r85b: genuine official audio on spaceless channel is 'official'",
      yt._classify_video_kind(RW_GENUINE['title'], RW_GENUINE['channel'],
                              RW_ARTIST, RW_SONG)['kind'] == 'official')
with patch.object(yt, '_fetch_candidates',
                  return_value=[RW_LYRIC_FAKE, RW_GENUINE]):
    best, score, seen = yt._search_best(RW_ARTIST, RW_SONG,
                                        ['rod wave dope girl official music video',
                                         'rod wave dope girl'])
check("r85b: pick is the genuine official audio, not the lyric re-upload",
      best is not None and best['id'] == 'g9Yo1sLnbjo',
      f"picked {best['id'] if best else None} score={score}")

print(f"\nround85: {passed} passed, {failed} failed")
