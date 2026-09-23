# Brooks Family Bot

Discord-бот семьи **Brooks** (GTA5RP). Первая версия — только состав.

## Стек

Python 3.11+ · discord.py 2.x · SQLite · SQLAlchemy 2.0 async · pydantic-settings · Ruff · pytest

Логика состава: [`docs/roster.md`](docs/roster.md).

## Запуск

1. В [Discord Developer Portal](https://discord.com/developers/applications) включи **Privileged Gateway Intent → Server Members Intent**.
2. Инвайт со скоупами `bot` + `applications.commands`. Права в канале состава: View Channel, Send Messages, Manage Messages, Read Message History.
3. Установка:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

4. В `.env` — `DISCORD_TOKEN`.
5. `python -m bot`

После старта бот сам собирает канал состава. Руководство: `/refresh`.

Новые фичи — отдельные файлы в `bot/cogs/` с `async def setup(bot)`. `main` только поднимает клиент и грузит коги.

## Каналы и роли

Зашиты в `bot/config.py` (не в `.env`).

| Что | ID |
|-----|-----|
| Канал состава | `1552347393993867274` |
| Owner-чат | `1453123004484554990` |

Ранги сверху вниз: Owner → AFK Owner → Dep. Owner → Head VZP → Recruiter → Пенсия → High → Main → Test.

`/refresh` и тег при ошибке: Owner, AFK Owner, Dep. Owner + роль руководства вне состава `1550837284927180882`.
