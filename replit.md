# Lyrics Master - Telegram Music Bot

## Architecture
- **bot.py**: Standalone Telegram bot worker using polling (single instance). This is the ONLY file that starts the bot.
- **app.py**: Pure Flask app for health check endpoints only. Does NOT initialize the bot.
- **wsgi.py**: WSGI entry point, imports Flask app from app.py.
- **main.py**: Flask dev server entry point. Does NOT start the bot.
- **handlers.py**: All Telegram command handlers.
- **input_parser.py**: Input parsing and normalization utilities with fallback search logic.
- **utils.py**: Lyrics analysis, mood detection, rhyme analysis, formatting.
- **services/**: External service integrations.

## Lyrics Provider Chain
1. **lrclib.net** (primary) — free, no API key, direct lookup + search
2. **lyrics.ovh** (fallback) — free, no API key, direct lookup only
3. **Genius API** (optional) — requires GENIUS_API_KEY secret

## Recommendation Provider Chain
1. **Spotify API** (if SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET set) — proper OAuth client_credentials flow
2. **Last.fm API** (if LASTFM_API_KEY set) — similar tracks endpoint
3. **Curated genre-matched pool** (always available) — 7 genres, 50+ songs with reasons

## YouTube Download
- Uses yt-dlp with format `bestvideo[height<=720]+bestaudio/best`
- ffmpeg merges video+audio streams, outputs MP4
- MP3 extraction uses FFmpegExtractAudio postprocessor at 192kbps
- Max duration: 10 minutes, max file size: 50MB (Telegram limit)

## Wiki Service
- Uses MediaWiki API (`en.wikipedia.org/w/api.php`) for real data
- Searches for music-related results, extracts intro text

## Subscribe System
- Persists to `subscribers.json` — survives bot restart
- APScheduler runs daily song delivery
- 30 curated songs in daily pool

## Quiz
- 40-song pool across multiple genres and eras
- Multiple choice (A/B/C/D) with streak tracking

## Natural Language Routing
- **intent_router.py**: Keyword-based intent detection for non-command messages
- Routes natural text like "lyrics water by tyla" or "who is drake" to existing command handlers
- "X by Y" patterns are normalized to "Y - X" format for correct song+artist matching
- Trailing filler words (on, in, at, for, please) are stripped from cleaned queries
- Quiz answers (A/B/C/D) take priority over NL routing when a quiz is active
- Ambiguous 1–3 word messages show clarification buttons (Artist Profile, Song Dashboard, Lyrics, YouTube, Similar)
- Messages starting with `/` bypass the router entirely
- Supported intents: lyrics, recommend, artist, youtube, download, mp3, trending, translate, analyze, stats, song, top, random, quiz, subscribe, unsubscribe

## Inline Action Buttons
- **buttons.py**: Builds InlineKeyboardMarkup for post-result quick actions
- Lyrics results: Analyze, Translate, Video, Similar
- Song dashboard: Full Lyrics, Analyze, Translate, Video, Similar
- Artist profile: Top Song, Video, Wiki, Similar
- Recommendations: Lyrics, Analyze, Video
- Trending/Top results: Lyrics, Song Dashboard (for #1 song)
- **callback_query_handler** in handlers.py routes button presses to existing command handlers

## Commands (20 total)
/start, /help, /song, /lyrics, /stats, /recommend, /analyze, /translate, /artist, /top, /random, /youtube, /download, /mp3, /quiz, /endquiz, /wiki, /trending, /subscribe, /unsubscribe

### New Commands
- **/song** — Full song dashboard (lyrics preview, YouTube, stats, mood, themes, 3 recommendations)
- **/top** — Top songs by genre (afrobeats, pop, rap, rnb, rock, latin, country, kpop + aliases)
- **/random** — Random song pick with lyrics preview, YouTube link, and similar songs
- **/artist** — Enhanced artist profile card with Wikipedia + YouTube links

## Workflows
- **Flask Server**: `gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 2 --timeout 0 wsgi:app` — health checks only
- **Telegram Bot**: `python bot.py` — the bot polling worker

## Deployment
- Target: Reserved VM (GCE) background worker
- Run command: `python bot.py`
- `ignorePorts = true` (no HTTP needed in production)

## Critical Rules
- NEVER start the bot from app.py or main.py — only bot.py
- NEVER run multiple bot instances (causes Telegram conflict errors)
- Keep `--workers 1` in gunicorn to prevent duplicate Flask instances
- Always clear webhook before starting polling (`delete_webhook`)

## Environment Variables
- TELEGRAM_TOKEN (required), DATABASE_URL
- GENIUS_API_KEY (optional), LASTFM_API_KEY (optional)
- SPOTIFY_CLIENT_ID (optional), SPOTIFY_CLIENT_SECRET (optional)
