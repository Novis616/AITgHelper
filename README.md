# AITgHelper

AITgHelper is a local-first Telegram assistant for saving notes, handling
forwarded messages, and creating simple one-time reminders from natural text.
It is built with Python 3.13, aiogram 3.x, SQLAlchemy, Alembic, SQLite, and a
configurable OpenAI-compatible AI provider.

The project is intended for personal use first. Runtime data, logs, local
configuration, and API keys stay on your machine.

## MVP Features

- Telegram bot with `/start` and `/help`.
- Russian and English bot replies.
- Saving regular text messages as notes.
- Saving forwarded text messages as notes with available Telegram source
  metadata.
- Listing and deleting notes.
- Creating simple one-time reminders from text such as `remind me tomorrow at
  18:00 to buy groceries`.
- Listing and deleting reminders.
- Reminder delivery through an in-process APScheduler job.
- Startup recovery for scheduled reminders stored in the database.
- Basic user timezone handling, with dates stored in UTC.
- AI message interpretation through either OpenAI or OpenRouter.
- Local storage of AI request history for debugging.
- SQLite database managed through SQLAlchemy 2.x and Alembic migrations.
- Automated tests for services, repositories, bot handlers, AI parsing, and
  scheduler behavior.

## Requirements

- Python `>=3.13,<3.14`
- Git
- A Telegram bot token from BotFather
- An OpenAI API key or an OpenRouter API key
- SQLite, included with Python for the default local setup
- Docker Desktop, if you want to run the bot in a container

## Configuration

Copy the example environment file and fill in local values:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

Example structure:

```dotenv
TELEGRAM_BOT_TOKEN=

AI_PROVIDER=openai
OPENAI_API_KEY=
OPENROUTER_API_KEY=
AI_MODEL=

APP_ENV=local
LOG_LEVEL=INFO
DEFAULT_TIMEZONE=Europe/Moscow
ENCRYPTION_ENABLED=true
APP_ENCRYPTION_KEY=replace-with-generated-fernet-key

DATABASE_URL=sqlite+aiosqlite:///./data/aitghelper.sqlite3

ALLOWED_TELEGRAM_USER_IDS=
```

Notes:

- `TELEGRAM_BOT_TOKEN` is required to run the bot.
- `AI_PROVIDER` must be `openai` or `openrouter`.
- Set `OPENAI_API_KEY` when `AI_PROVIDER=openai`.
- Set `OPENROUTER_API_KEY` when `AI_PROVIDER=openrouter`.
- `AI_MODEL` must contain a model name supported by the selected provider.
- `APP_ENCRYPTION_KEY` is required when `ENCRYPTION_ENABLED=true`. Use a Fernet
  key generated locally and keep it only in `.env`.
- `ALLOWED_TELEGRAM_USER_IDS` is optional. Leave it empty to allow any user who
  can reach the bot, or set comma-separated numeric Telegram user IDs such as
  `123456789,987654321`.
- Do not put real secrets in `.env.example`, source code, tests, or commits.

## Local Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project with development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Create the local database schema:

```powershell
python -m alembic upgrade head
```

Run the bot:

```powershell
python -m app
```

The same entry point is also available after installation:

```powershell
aitghelper
```

## Tests

Run the full test suite:

```powershell
python -m pytest
```

Optional syntax/import check:

```powershell
python -m compileall app tests migrations
```

Check the current Alembic migration revision:

```powershell
python -m alembic current
```

If your local `.env` restricts access, make sure `ALLOWED_TELEGRAM_USER_IDS`
contains only numeric IDs. Usernames such as `@username` are not valid there.

## Docker

The Docker setup uses the same local `.env` file and stores SQLite data under
`data/` on your machine. Alembic migrations run automatically before the bot
starts.

Build and start the bot:

```powershell
docker compose up --build -d
```

View logs:

```powershell
docker compose logs -f bot
```

Stop the bot:

```powershell
docker compose down
```

Run migrations without starting polling:

```powershell
docker compose run --rm bot python -m alembic upgrade head
```

## Data And Secrets

The default SQLite database is stored under `data/`. Local environment files,
database files, logs, caches, and other runtime artifacts should not be
committed.

Sensitive user content is encrypted before it is stored in the database. This
protects against direct reading of the SQLite file, but it does not protect a
server or application process that is fully compromised and can access the
runtime encryption key.

Before publishing changes, it is useful to check:

```powershell
git status --short
git ls-files .env data logs *.sqlite *.sqlite3 *.db
```

The second command should not list local secrets or database files.
