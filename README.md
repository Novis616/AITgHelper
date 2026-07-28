# AITgHelper

AITgHelper is a personal Telegram assistant built with Python and aiogram.

The project is being prepared as a local-first bot for saving notes, handling
forwarded Telegram messages, creating simple one-time reminders, and using a
configurable AI provider for message interpretation.

## Status

The repository currently contains the project skeleton, async database layer,
service layer, and a basic aiogram 3.x Telegram bot. The bot can respond to
`/start` and `/help`, save regular text messages as notes, and save forwarded
text messages as notes.

Reminder scheduling and AI interpretation are intentionally not implemented yet.

## Requirements

- Python 3.13
- A Telegram bot token for future bot runs
- An OpenAI or OpenRouter API key for future AI features

## Configuration

Copy `.env.example` to `.env` and fill in local values. Real tokens, API keys,
local databases, logs, and private data must stay out of Git.

## Development

Install dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run the import test:

```powershell
python -m pytest
```

Apply database migrations:

```powershell
alembic upgrade head
```

Run the Telegram bot:

```powershell
python -m app
```
