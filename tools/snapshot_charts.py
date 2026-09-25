#!/usr/bin/env python3
"""Daily chart-history snapshotter (feeds /trending velocity, incl. v2).

Fetches the country charts (us/kr/ng) and every Apple RSS genre chart once
and lets the snapshot hooks in artist_service persist one dated file each.
Idempotent per day; never raises (a missed day just means a thinner window).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import artist_service as a

GENRE_CHARTS = [  # (apple_genre_id, country)
    ('14', 'us'),  # pop
    ('18', 'us'),  # rap
    ('15', 'us'),  # rnb / soul
    ('21', 'us'),  # rock
    ('6', 'us'),   # country
    ('12', 'us'),  # latin
]

COUNTRY_CHARTS = ['us', 'kr', 'ng']


def main() -> int:
    ok = 0
    for country in COUNTRY_CHARTS:
        try:
            if a._get_cached_chart(country):
                ok += 1
        except Exception:
            pass
    for gid, country in GENRE_CHARTS:
        try:
            if a._get_cached_genre_chart(gid, country):
                ok += 1
        except Exception:
            pass
    print(f"snapshot_charts: {ok}/{len(COUNTRY_CHARTS) + len(GENRE_CHARTS)} "
          f"charts snapshotted")
    return 0


if __name__ == '__main__':
    sys.exit(main())
