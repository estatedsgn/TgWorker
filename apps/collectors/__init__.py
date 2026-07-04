from apps.collectors.freelancehunt import FreelanceHuntCollector
from apps.collectors.rss import RssCollector

# Поллинг-коллекторы по значению sources.type. Telegram живёт отдельно —
# он событийный, см. apps.collectors.telegram.register_telegram.
COLLECTORS = {
    "rss": RssCollector,
    "freelancehunt": FreelanceHuntCollector,
}
