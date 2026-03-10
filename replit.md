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

## Commands (17 total)
/start, /help, /lyrics, /stats, /recommend, /analyze, /translate, /youtube, /download, /mp3, /quiz, /endquiz, /wiki, /artist, /trending, /subscribe, /unsubscribe

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
