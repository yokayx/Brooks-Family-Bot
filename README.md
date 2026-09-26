# Brooks Family Bot

## Стек

Python 3.11+ · discord.py 2.x · SQLite · SQLAlchemy 2.0 async · pydantic-settings · Ruff · pytest

Логика состава: [`docs/roster.md`](docs/roster.md).

После старта бот сам собирает канал состава. Руководство: `/refresh`.

Итоги ВЗП Brooks (Richman) — в канал `1552367826906521620`, источник `vzp-launcher.pro/api/wars` (неофициально). `/vzp` — ручная проверка. Когда нам забивают деф, бот сам пишет в канал и создаёт сбор без статиков `DEF vs {семья}`.

Сборы: `/плюсы` у руководства, кнопки ➕/➖ у семьи. Логика: [`docs/plus.md`](docs/plus.md).

Заявки в семью: меню со списком в канале `1453123004308390116` (Main — «Заявка на Young», VZP — «Заявка на Test»), панель управления в канале `1553239900176908289`, тикеты в категориях открытых/закрытых. Логика: [`docs/applications.md`](docs/applications.md).

Логи сервера (сообщения, заходы/выходы и инвайты, роли, модерация, войс, каналы, аудит): [`docs/logs.md`](docs/logs.md). ID каналов логов — константы `LOG_*_CHANNEL_ID` в `bot/config.py`, сейчас `0` (ждут подстановки).

Отдельные файлы в `bot/cogs/` с `async def setup(bot)`. `main` только поднимает клиент и грузит коги.

## Каналы и роли

Зашиты в `bot/config.py` (не в `.env`).

Ранги сверху вниз: Owner → AFK Owner → Dep. Owner → Head VZP → Recruiter → Пенсия → High → Main → Test.

`/refresh` и тег при ошибке: Owner, AFK Owner, Dep. Owner `1550837284927180882`.
