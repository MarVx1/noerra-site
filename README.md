# Noerra

Scientific intelligence bot for collecting neuroscience and psychology sources,
scoring them, preparing editorial drafts, and publishing approved posts to
Telegram through Telegraph.

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in your real values:

```env
BOT_TOKEN=
ADMIN_CHAT_ID=0
CHANNEL_ID=@your_channel
TELEGRAPH_TOKEN=
```

3. Start the bot:

```bash
python main.py
```

## Tests

Use a separate database for tests so local production data is not touched:

```bash
DATABASE_PATH=test_noerra.db python -m unittest discover -s tests -p "test_*.py"
```

On PowerShell:

```powershell
$env:DATABASE_PATH = "test_noerra.db"
$env:BOT_TOKEN = "123456:test"
$env:ADMIN_CHAT_ID = "1"
$env:CHANNEL_ID = "@test"
python -m unittest discover -s tests -p "test_*.py"
```

## Project Layout

- `main.py` - application entrypoint.
- `config/` - runtime settings loaded from environment variables.
- `parsers/` - PubMed, arXiv, RSS, CyberLeninka, and YouTube source parsers.
- `scoring/` - article quality scoring.
- `classifier/` - topic classification.
- `adaptation/` - editorial planning, text generation, criticism, and publication models.
- `database/` - SQLite persistence.
- `bot/` - Telegram moderation interface.
- `publisher/` - Telegraph and Telegram publication helpers.
- `scheduler/` - parsing pipeline and digest schedule.
- `tests/` - unit and integration tests.
