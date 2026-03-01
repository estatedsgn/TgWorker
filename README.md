# tg-leads-agent — Package 0 + Package 1

Каркас проекта для легитимной обработки Telegram-заявок через userbot (MTProto).

## Политика легитимности

- Разрешён исходящий контакт **только** для лидов с `consent=true`.
- Лиды с `consent=false` должны блокироваться бизнес-логикой отправки (в следующих пакетах).
- Все сущности привязаны к `account_id` для масштабирования на N аккаунтов.

## Структура репозитория

```text
.
├── apps/
│   ├── common/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── logging.py
│   │   └── models.py
│   ├── tg_listener/main.py
│   ├── tg_sender/
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

## 5) Smoke test сервисов

```bash
source .venv/bin/activate
python -m apps.worker.main
python -m apps.tg_listener.main
```

Ожидаемые логи:
- `worker started` / `listener started`
- `db connected`

В логах не печатаются секреты (`DATABASE_URL` не выводится полностью).

## 6) Конфиг переменных

Минимальный набор:
- `DATABASE_URL`
- `DEFAULT_ACCOUNT_ID`
- `LOG_LEVEL`
- `APP_ENV`
- `DRY_RUN`

См. `.env.example`.

## 7) Статусы лидов

Допустимые значения `leads.status`:
- `NEW`
- `WAITING_REPLY`
- `IN_DIALOG`
- `QUALIFIED`
- `WON`
- `LOST`
- `DNC`
- `ERROR`

## 8) Минимальное качество кода

В проект добавлен `ruff`:

```bash
source .venv/bin/activate
ruff check .
```
