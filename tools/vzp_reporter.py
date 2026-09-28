#!/usr/bin/env python3
"""Доставка данных о войнах ВЗП в бот Brooks.

Что делает: смотрит в папку (по умолчанию `vzp_outbox`), берёт файлы `*.json`
и отправляет каждый в служебный канал бота. Успешно отправленные переносит в
`vzp_outbox/sent`, битые — в `vzp_outbox/bad`.

Что НЕ делает: не собирает данные из игры. Откуда взять JSON — твоя часть;
этот скрипт только доставка, чтобы не зависеть от открытых портов и API бота.

Зависимостей нет — только стандартная библиотека.

Переменные окружения (или `.env` рядом со скриптом):
    DISCORD_TOKEN           токен бота (тот же, что у Brooks)
    VZP_INGEST_CHANNEL_ID   id служебного канала приёма
    VZP_OUTBOX              папка с файлами (по умолчанию ./vzp_outbox)
    VZP_POLL_SECONDS        как часто смотреть папку (по умолчанию 5)

Запуск:
    python tools/vzp_reporter.py          # крутится и ждёт файлы
    python tools/vzp_reporter.py --once   # отправить то, что лежит, и выйти
    python tools/vzp_reporter.py file.json
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "https://discord.com/api/v10"


def load_env(path: pathlib.Path) -> None:
    """Мини-загрузчик .env, чтобы не тащить python-dotenv на машину игрока."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


class Reporter:
    def __init__(self, token: str, channel_id: str, outbox: pathlib.Path) -> None:
        self._token = token
        self._channel_id = channel_id
        self.outbox = outbox
        self.sent = outbox / "sent"
        self.bad = outbox / "bad"
        for folder in (self.outbox, self.sent, self.bad):
            folder.mkdir(parents=True, exist_ok=True)

    def send(self, path: pathlib.Path) -> bool:
        """Отправляем файлом: так нет лимита на длину сообщения."""
        boundary = uuid.uuid4().hex
        meta = json.dumps({"content": f"vzp: {path.name}"}).encode()
        body = b"".join(
            [
                (
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="payload_json"\r\n'
                    "Content-Type: application/json\r\n\r\n"
                ).encode(),
                meta,
                b"\r\n",
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="files[0]"; '
                    f'filename="{path.name}"\r\n'
                    "Content-Type: application/json\r\n\r\n"
                ).encode(),
                path.read_bytes(),
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        request = urllib.request.Request(
            f"{API}/channels/{self._channel_id}/messages",
            data=body,
            headers={
                "Authorization": f"Bot {self._token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return 200 <= response.status < 300
        except urllib.error.HTTPError as exc:
            print(f"[{path.name}] discord вернул {exc.code}: {exc.read()[:300]!r}")
            return False
        except urllib.error.URLError as exc:
            print(f"[{path.name}] нет связи: {exc.reason}")
            return False

    def process(self, path: pathlib.Path) -> None:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            print(f"[{path.name}] не JSON: {exc}")
            path.replace(self.bad / path.name)
            return

        if self.send(path):
            print(f"[{path.name}] отправлено")
            path.replace(self.sent / path.name)
        else:
            path.replace(self.bad / path.name)

    def pending(self) -> list[pathlib.Path]:
        return sorted(
            item
            for item in self.outbox.glob("*.json")
            if item.is_file() and item.stat().st_size > 0
        )

    def run(self, *, once: bool = False, interval: float = 5.0) -> None:
        print(f"смотрю {self.outbox.resolve()} -> канал {self._channel_id}")
        while True:
            files = self.pending()
            for path in files:
                # Файл мог ещё писаться: даём ему остыть.
                time.sleep(0.3)
                self.process(path)
            if once:
                return
            time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Отправка JSON с войнами ВЗП в бот Brooks")
    parser.add_argument("file", nargs="?", help="отправить один файл и выйти")
    parser.add_argument("--once", action="store_true", help="отправить всё, что лежит, и выйти")
    args = parser.parse_args()

    load_env(pathlib.Path(__file__).with_name(".env"))

    token = os.environ.get("DISCORD_TOKEN", "").strip()
    channel_id = os.environ.get("VZP_INGEST_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        print("нужны DISCORD_TOKEN и VZP_INGEST_CHANNEL_ID (в .env рядом со скриптом)")
        return 2

    outbox = pathlib.Path(os.environ.get("VZP_OUTBOX", "vzp_outbox")).expanduser()
    reporter = Reporter(token, channel_id, outbox)

    if args.file:
        reporter.process(pathlib.Path(args.file).expanduser())
        return 0

    interval = float(os.environ.get("VZP_POLL_SECONDS", "5") or 5)
    reporter.run(once=args.once, interval=interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
