# Docker

Бот в контейнере, SQLite на хосте в `./data`.

## Запуск

```bash
cp .env.example .env
# в .env — DISCORD_TOKEN
mkdir -p data
docker compose up -d --build
docker compose logs -f bot
```

Стоп: `docker compose down`. База остаётся в `data/brooks.db`.

Если контейнер не может писать в `data/` (permission denied):

```bash
sudo chown -R 1000:1000 data
```

В контейнере пользователь `brooks` (uid 1000).

## Что внутри

| Файл | Зачем |
|------|--------|
| `Dockerfile` | Python 3.12-slim, `pip install .`, non-root |
| `docker-compose.yml` | restart, том `./data`, логи с ротацией, `init` |
| `.dockerignore` | не тащить `.venv`, `.git`, `.env`, тесты в образ |

Токен только через `.env` / `env_file`, в образ не копируется.

`DATABASE_URL` в compose зашит на `sqlite+aiosqlite:///data/brooks.db` — путь внутри контейнера, это том.
