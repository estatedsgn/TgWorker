# tg-leads-agent — Package 0 + Package 1 + Package 2

Каркас проекта для легитимной обработки Telegram-заявок через userbot (MTProto).

## Политика легитимности

- Разрешён исходящий контакт **только** для лидов с `consent=true`.
- Лиды с `consent=false` должны блокироваться бизнес-логикой отправки.
- Если пользователь просит не писать (`не писать/отпишись/stop`), лид переводится в `DNC`.
- Все сущности привязаны к `account_id` для масштабирования на N аккаунтов.

## Структура репозитория

```text
.
├── apps/
│   ├── common/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── logging.py
│   │   ├── models.py
│   │   └── telegram_client.py
│   ├── tg_listener/main.py
│   ├── tg_sender/main.py
│   └── worker/main.py
├── deploy/docker-compose.yml
├── migrations/
├── scripts/seed.py
├── .env.example
├── alembic.ini
└── pyproject.toml
```

## 1) Подготовка

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 2) Поднять Postgres

```bash
docker compose -f deploy/docker-compose.yml --env-file .env up -d
docker ps
```

## 3) Применить миграции

```bash
source .venv/bin/activate
alembic upgrade head
```

## 4) Засидить тестовые данные

```bash
source .venv/bin/activate
python scripts/seed.py
```

Что создаётся:
- `accounts.acc_01` (или `DEFAULT_ACCOUNT_ID` из env), лимиты: `50/20`, задержка `20..90`, timezone `Europe/Berlin`.
- `leads.lead_1`: `consent=true`, `status=NEW`, `next_action_at=now`, `tg_username=placeholder_consent_username`.
- `leads.lead_2`: `consent=false`, `status=NEW` (контрольный лид для блокировки исходящей коммуникации).

Seed идемпотентный: повторный запуск обновляет/переиспользует записи, не плодит дубликаты.

## 5) Telegram (Telethon) — первый логин и сессия

Нужные env:
- `TG_API_ID`
- `TG_API_HASH`
- `TG_SESSION_PATH` (например `/data/acc_01.session`)
- `DEFAULT_ACCOUNT_ID=acc_01`
- `DRY_RUN=true|false`

Рекомендуется хранить `.session` на volume `/data` (персистентно).

Одноразовый интерактивный логин:

```bash
source .venv/bin/activate
python - <<'PY'
import os
from telethon import TelegramClient

client = TelegramClient(
    os.environ["TG_SESSION_PATH"],
    int(os.environ["TG_API_ID"]),
    os.environ["TG_API_HASH"],
)
with client:
    print("Telethon session created")
PY
```

## 6) Smoke test сервисов

```bash
source .venv/bin/activate
python -m apps.worker.main
python -m apps.tg_listener.main
```

Ожидаемые логи:
- `worker started` / `listener started`
- `db connected`

## 7) Отправка сообщения

### Dry run (рекомендуется сначала)

```bash
DRY_RUN=true python -m apps.tg_sender.main lead_1 "Привет! Это тест"
```

- В Telegram ничего не отправляется.
- В `messages` пишется `OUT` с `meta_json={"dry_run": true}`.

### Реальная отправка

```bash
DRY_RUN=false python -m apps.tg_sender.main lead_1 "Привет! Это тест"
```

- Через Telethon отправляется сообщение по `tg_peer_id` или `tg_username`.
- В `messages` сохраняется `OUT` и `tg_message_id`.

## 8) Listener входящих

`apps.tg_listener.main` слушает `NewMessage(incoming=True)`:
- поиск лида: сначала `tg_peer_id`, потом `tg_username`
- неизвестные лиды игнорируются (автосоздания нет)
- дедуп входящих по `(lead_id, tg_message_id)`
- запись `messages(direction=IN)`
- обновление `lead` (`last_message_in`, `last_in_at`, `IN_DIALOG`, `next_action_at`)
- обработка `не писать/отпишись/stop` -> `dnc=true`, `status=DNC`

## 9) Минимальное качество кода

```bash
source .venv/bin/activate
ruff check .
```
