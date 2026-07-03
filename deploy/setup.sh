#!/usr/bin/env bash
# One-shot server setup for the Telegram digest bot.
# Run as root from the repo root: bash deploy/setup.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_NAME="tg_leads"
DB_USER="tg_leads"
DB_PASS="${DB_PASS:-tg_leads}"

echo "==> App dir: $APP_DIR"

echo "==> Installing system packages"
apt-get update -q
apt-get install -y -q python3-venv python3-pip postgresql

echo "==> Configuring PostgreSQL"
systemctl enable --now postgresql
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 ||
  sudo -u postgres psql -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS'"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 ||
  sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"

echo "==> Python venv + dependencies"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q -U pip
./.venv/bin/pip install -q -e .

echo "==> .env"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg2://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME|" .env
  sed -i "s|^TG_SESSION_PATH=.*|TG_SESSION_PATH=$APP_DIR/data/acc_01.session|" .env
  sed -i "s|^TG_BOT_SESSION_PATH=.*|TG_BOT_SESSION_PATH=$APP_DIR/data/digest_bot.session|" .env
  echo "    Created .env — fill in TG_API_ID, TG_API_HASH, TG_BOT_TOKEN, ANTHROPIC_API_KEY"
else
  echo "    .env already exists, leaving as is"
fi
mkdir -p "$APP_DIR/data"

echo "==> Migrations"
set -a; . ./.env; set +a
if [ -n "${DATABASE_URL:-}" ]; then
  ./.venv/bin/alembic upgrade head
fi

echo "==> systemd unit"
sed "s|/opt/tg-leads-agent|$APP_DIR|g" deploy/digest-bot.service > /etc/systemd/system/digest-bot.service
systemctl daemon-reload
systemctl enable digest-bot

cat <<EOF

==> Done. Remaining manual steps:
1. Fill secrets in $APP_DIR/.env:
   TG_API_ID, TG_API_HASH (my.telegram.org), TG_BOT_TOKEN (@BotFather),
   ANTHROPIC_API_KEY, DIGEST_ALLOWED_USER_IDS (your Telegram user id)
2. One-time userbot login (asks for the code from Telegram):
   cd $APP_DIR && set -a && . ./.env && set +a && ./.venv/bin/python scripts/telegram_login.py
3. Start the bot:
   systemctl start digest-bot && journalctl -u digest-bot -f
EOF
