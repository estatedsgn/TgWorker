# announce-parser

Парсер объявлений о заказах на разработку. Собирает посты «ищу разработчика / нужен бот / сделать сайт» из Telegram-чатов и с фриланс-бирж, фильтрует по ключевым словам, дедуплицирует и складывает в Postgres. Ничего никому не отправляет — связь с заказчиками ведётся вручную.

## Источники (v1)

| Тип | Что это | Как подключается |
|---|---|---|
| `telegram` | Чаты и каналы с заказами | Telethon-юзербот слушает список чатов в реальном времени, опционально догружает историю (`backfill_limit`) |
| `rss` | FL.ru, Freelance.ru, Weblancer и любые другие RSS-ленты | Поллинг раз в `poll_interval_sec` (по умолчанию 300 с) с conditional GET |
| `freelancehunt` | FreelanceHunt | Официальный API v2, нужен токен `FREELANCEHUNT_TOKEN` |

Каждый источник — строка в таблице `sources`. Добавить новый чат или ленту — один INSERT, код трогать не нужно:

```sql
INSERT INTO sources (type, name, config)
VALUES ('telegram', 'Фриланс Таверна', '{"chat": "@freelancetaverna", "backfill_limit": 200}');

INSERT INTO sources (type, name, config)
VALUES ('rss', 'Habr Freelance', '{"url": "https://freelance.habr.com/...", "poll_interval_sec": 300}');
```

Поля `config`: `chat`, `backfill_limit` (telegram); `url`, `poll_interval_sec` (rss); `skip_filter: true` — не применять фильтр ключевых слов (для лент, где и так только заказы).

Новый тип источника (Kwork, HH.ru, VK, HTML-скраперы) — один класс-коллектор в `apps/collectors/` + запись в реестр `COLLECTORS` в `apps/collectors/__init__.py`.

## Пайплайн

```
коллекторы → фильтр ключевых слов → дедупликация → announcements
```

- **Фильтр** — таблица `keywords` (`include`/`exclude`), нормализованный поиск подстроки (регистр, ё/е, пробелы не важны). `exclude` побеждает: «Разработчик, вот резюме» отбрасывается. Слова правятся прямо в БД, парсер перечитывает их раз в `KEYWORDS_RELOAD_SEC` без рестарта.
- **Дедупликация** — двухслойная: по `(source_id, external_id)` (повторные выдачи одного источника) и по `text_hash` (один заказ, запощенный в пять чатов, сохранится один раз).
- **`announcements`** — текст, ссылка, контакт автора (`author_username` для Telegram), совпавшие ключевые слова, `status` (`new`/`processed` — переключай вручную в любом DB-клиенте).

## Запуск

```bash
cp .env.example .env            # заполнить DATABASE_URL и, при необходимости, TG_*/FREELANCEHUNT_TOKEN
pip install -e ".[dev]"

docker compose -f deploy/docker-compose.yml up -d   # Postgres
alembic upgrade head                                 # схема
python scripts/seed_sources.py                       # стартовые источники и ключевые слова

# только для telegram-источников: первый интерактивный вход
python scripts/telegram_login.py

python -m apps.parser.main
```

Требования для Telegram: `TG_API_ID`/`TG_API_HASH` с https://my.telegram.org, аккаунт-юзербот должен **состоять** в парсируемых группах и быть **подписан** на каналы — иначе апдейты не приходят. Прокси при необходимости — `PROXY_*` в `.env`.

Рестарты при падении — внешние: `restart: unless-stopped` в docker или `Restart=always` в systemd.

## Структура

```
apps/
  common/       конфиг, БД, логирование, Telethon-клиент, модели
  collectors/   telegram.py, rss.py, freelancehunt.py, base.py (RawItem, реестр)
  pipeline/     normalize.py, filter.py, process.py (фильтр → дедуп → insert)
  parser/       main.py — entrypoint, один процесс, один event loop
scripts/        telegram_login.py, seed_sources.py
tests/          pytest, sqlite in-memory, фикстура RSS
```

## Тесты и линт

```bash
DATABASE_URL="sqlite://" pytest
ruff check .
```
