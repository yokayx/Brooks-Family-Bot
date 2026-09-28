# Приём данных ВЗП от своего инструмента

Публичный API `vzp-launcher.pro` — источник по умолчанию. Если данные нужно
брать из игры (когда игрок в сети), бот может принять их со стороны:

```
твой коллектор (запускается у игрока)
        │  кладёт *.json в папку
        ▼
tools/vzp_reporter.py
        │  отправляет файл в служебный канал Discord
        ▼
бот: bot/cogs/vzp.py (on_message)
        │  нормализует (bot/vzp/ingest.py), публикует итог, ловит забивы
        ▼
канал ВЗП 1552367826906521620
```

## Что делает бот

- принимает JSON **файлом** или текстом сообщения в канале `VZP_INGEST_CHANNEL_ID`
  (`bot/config.py`, потом подставим id канала);
- приводит ключи к каноническим (`bot/vzp/ingest.py`): `war_id→id`,
  `server→server_name`, `attacker→attacker_name`, `winner→winner_side`,
  `players→participants`, `nick/name→player_name`, `accuracy→hit_percent`,
  `hs→headshot_percent`, `side/team→family_side` и т.д.;
- публикует тот же эмбед, что и по API (`build_result_embed`);
- проверяет забивы на нас (`is_incoming_defense`) — создаёт сбор `DEF vs …`;
- не публикует повторно уже отправленные войны (`already_posted`).

## Формат JSON

Одна война или список; поля — как в API, синонимы разрешены.

```json
{
  "wars": [
    {
      "id": "76a842d5-f43b-4781-9a94-59bdea0ae20f",
      "server_name": "RICHMAN",
      "attacker_name": "Brooks",
      "defender_name": "Vagos",
      "winner_side": "attacker",
      "status": "finished",
      "attacker_score": 3,
      "defender_score": 1,
      "territory": "Точка 5",
      "map_name": "Paleto",
      "started_at": "2026-09-26T18:00:00Z",
      "ended_at": "2026-09-26T18:20:00Z",
      "participants": [
        {
          "player_name": "Klyde_Brooks",
          "family_side": "attacker",
          "kills": 3,
          "damage": 900,
          "hit_percent": 26,
          "headshot_percent": 5.6
        }
      ]
    }
  ]
}
```

## Запуск доставщика (машина игрока)

```bash
cd tools
printf 'DISCORD_TOKEN=токен_бота\nVZP_INGEST_CHANNEL_ID=id_канала\n' > .env
python vzp_reporter.py          # крутится, шлёт новые *.json из ./vzp_outbox
python vzp_reporter.py --once   # отправить, что лежит, и выйти
python vzp_reporter.py war.json # один файл
```

Успешно отправленное уходит в `vzp_outbox/sent`, битое — в `vzp_outbox/bad`.
Зависимостей нет, только стандартная библиотека.

Коллектор (что именно собирать из игры и как) — не часть этого репозитория:
боту нужен только JSON в папке.
