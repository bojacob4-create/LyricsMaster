# Lyrics Master - Telegram Music Bot

## Architecture
- **bot.py**: Standalone Telegram bot worker using polling (single instance). This is the ONLY file that starts the bot.
- **app.py**: Pure Flask app for health check endpoints only. Does NOT initialize the bot.
- **wsgi.py**: WSGI entry point, imports Flask app from app.py.
- **main.py**: Flask dev server entry point. Does NOT start the bot.
- **handlers.py**: All Telegram command handlers.
- **input_parser.py**: Input parsing and normalization utilities with fallback search logic.
- **services/**: External service integrations.

## Lyrics Provider Chain
1. **lrclib.net** (primary) — free, no API key, direct lookup + search
2. **lyrics.ovh** (fallback) — free, no API key, direct lookup only
3. **Genius API** (optional) — requires GENIUS_API_KEY secret to be set

## Input Parsing
All song-related commands accept flexible input formats:
- `/lyrics Tyla - Water` (artist - song)
- `/lyrics Water Tyla` (words, auto-split)
- `/lyrics Water` (song only, searched)
- Handles quotes, extra spaces, hyphens, em-dashes

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

## Commands
/start, /help, /lyrics, /stats, /recommend, /quiz, /endquiz, /translate, /youtube, /analyze, /subscribe, /unsubscribe, /download, /wiki

## Environment Variables
- TELEGRAM_TOKEN, DATABASE_URL, GENIUS_API_KEY (optional), LASTFM_API_KEY
- SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
