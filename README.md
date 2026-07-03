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

Одноразовый интерактивный логин (рекомендуемый способ):

```bash
source .venv/bin/activate
python scripts/telegram_login.py
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
- `telegram connected`

`apps.tg_listener.main` после старта **НЕ должен завершаться сразу**: процесс остаётся активным до отключения Telegram.

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

## Digest bot — ежедневный дайджест из Telegram-каналов

Модуль `apps/digest` собирает посты из 10-30 каналов и раз в день присылает короткий дайджест
самого важного со ссылками на оригинальные посты.

### Как это работает

1. **Сбор** (`collect`): userbot читает новые посты из подписанных каналов и складывает их в
   `channel_posts` (текст, просмотры, репосты, наличие медиа).
2. **Кластеризация** (бесплатно, локально): тексты нормализуются, считается Jaccard-схожесть по
   3-словным шинглам, похожие посты из разных каналов объединяются в кластер. **Повтор новости в
   нескольких каналах — главный сигнал важности.**
3. **Пре-скоринг** (бесплатно): `2.0·log2(1+каналов) + вовлечённость (просмотры относительно
   медианы канала) + свежесть + бонус за медиа`. Отбираются топ-`DIGEST_LLM_CANDIDATES` кластеров.
4. **LLM** (один дешёвый вызов в день): Claude Haiku 4.5 оценивает интересность 1-10, отсеивает
   рекламу/розыгрыши и пишет заголовок + 1-2 предложения по каждой новости (structured JSON).
   Стоимость ~$0.03-0.08 в день при 30 каналах.
5. **Дайджест**: итоговый балл = `LLM-интерес + 2·повторяемость + вовлечённость`, берутся
   топ-`DIGEST_MAX_ITEMS`, форматируются со ссылками `t.me/канал/пост` и отправляются в
   `DIGEST_TARGET_CHAT` (по умолчанию — Избранное).

### Настройка

В `.env` добавьте `ANTHROPIC_API_KEY` (модель настраивается через `LLM_MODEL`,
по умолчанию `claude-haiku-4-5`), затем примените миграции: `alembic upgrade head`.

### Telegram-бот (основной способ)

Дайджестом управляет обычный бот (токен из @BotFather). Внутри процесса работают два клиента:
userbot читает каналы (Bot API не умеет читать чужие каналы), бот — интерфейс и доставка.

```bash
python -m apps.tg_bot.main
```

Команды бота:
- `/digest` — самое интересное за последние сутки, прямо сейчас
- `/add @канал` / `/remove @канал` / `/list` — управление подборкой
- `/start` — подписка на ежедневную рассылку (после `DIGEST_HOUR`)

Доступ: `DIGEST_ALLOWED_USER_IDS=123,456` (пусто — бот отвечает всем, для личного
использования обязательно ограничьте).

Автозапуск на сервере (systemd):

```bash
sudo cp deploy/digest-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now digest-bot
journalctl -u digest-bot -f
```

### CLI (альтернатива без бота)

```bash
# подписки
python -m apps.digest.main add-channel @durov
python -m apps.digest.main list-channels
python -m apps.digest.main remove-channel @durov

# разовый прогон
python -m apps.digest.main collect          # собрать новые посты
python -m apps.digest.main build            # собрать дайджест и напечатать в консоль
python -m apps.digest.main build --send     # собрать и отправить в Telegram

# демон: сбор каждые DIGEST_COLLECT_INTERVAL_MIN минут,
# дайджест ежедневно после DIGEST_HOUR (таймзона DIGEST_TIMEZONE)
python -m apps.digest.main run
```

### Env-переменные

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | ключ Anthropic API (обязателен для `build`) |
| `TG_BOT_TOKEN` | — | токен бота из @BotFather |
| `TG_BOT_SESSION_PATH` | `digest_bot.session` | сессия бот-клиента |
| `DIGEST_ALLOWED_USER_IDS` | пусто | кому разрешено пользоваться ботом (id через запятую) |
| `LLM_MODEL` | `claude-haiku-4-5` | модель; можно поднять до `claude-sonnet-5` для качества |
| `DIGEST_TARGET_CHAT` | `me` | куда слать: `me`, `@username` или id чата |
| `DIGEST_HOUR` | `9` | час отправки дайджеста (локальное время) |
| `DIGEST_TIMEZONE` | `Europe/Berlin` | таймзона для `DIGEST_HOUR` |
| `DIGEST_MAX_ITEMS` | `12` | максимум новостей в дайджесте |
| `DIGEST_LLM_CANDIDATES` | `40` | сколько кластеров отправлять в LLM |
| `DIGEST_WINDOW_HOURS` | `24` | окно свежести постов |
| `DIGEST_COLLECT_INTERVAL_MIN` | `30` | период сбора постов в демоне |

## 9) Минимальное качество кода

```bash
source .venv/bin/activate
ruff check .
```


## E2E on VPS

Ниже runbook для Ubuntu-сервера, который можно повторить с нуля.

```bash
cd /opt/tg-leads-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# заполните TG_API_ID/TG_API_HASH/TG_SESSION_PATH и DATABASE_URL в .env
```

1) Поднять Postgres:

```bash
docker compose -f deploy/docker-compose.yml --env-file .env up -d
docker ps --filter name=tg_leads_postgres
```

2) Применить миграции:

```bash
source .venv/bin/activate
set -a; source .env; set +a
alembic upgrade head
```

3) Засидить тестовые данные:

```bash
source .venv/bin/activate
set -a; source .env; set +a
python scripts/seed.py
```

Seed создаёт `lead_test_1` с `consent=true` и `tg_username=placeholder_test_username`.
Перед тестом замените username на реальный в БД, например:

```sql
update leads set tg_username='real_username' where lead_id='lead_test_1';
```

4) Экспорт env в shell (если ещё не сделали):

```bash
set -a; source .env; set +a
```

5) Создать Telethon session:

```bash
source .venv/bin/activate
python scripts/telegram_login.py
```

После первого логина должен появиться файл `TG_SESSION_PATH` (`*.session`).

6) Запустить listener (отдельный терминал/tmux):

```bash
source .venv/bin/activate
set -a; source .env; set +a
python -m apps.tg_listener.main
```

Ожидаемые логи: `listener started`, `db connected`, `telegram connected`.

7) Отправить тестовое сообщение через sender:

```bash
source .venv/bin/activate
set -a; source .env; set +a
DRY_RUN=false python -m apps.tg_sender.main lead_test_1 "E2E test message"
```

8) SQL-проверки:

```sql
select lead_id, status, dnc, tg_peer_id, last_message_in, last_message_out, last_in_at, last_out_at
from leads
where lead_id='lead_test_1';

select lead_id, direction, text, tg_message_id, ts
from messages
where lead_id='lead_test_1'
order by ts desc
limit 5;
```

Ожидаемый результат:
- после sender есть запись `OUT` в `messages`;
- после ответа с телефона listener пишет `IN` и обновляет `leads.status` на `IN_DIALOG`;
- повторно обработанные входящие с тем же `tg_message_id` игнорируются (dedup).


### Quick e2e flow (manual_1)

```sql
insert into leads (lead_id, account_id, tg_username, consent, status, stage, attempts_count, dnc)
values ('manual_1', 'acc_01', 'your_test_username', true, 'NEW', 0, 0, false)
on conflict (lead_id) do update set tg_username=excluded.tg_username, consent=true, dnc=false, status='NEW';
```

```bash
python -m apps.tg_listener.main
# in second shell
python -m apps.tg_sender.main manual_1 "hello"
```
