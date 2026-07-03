from __future__ import annotations

from apps.common.llm import complete_json
from apps.common.logging import get_logger
from apps.digest.scoring import ScoredCluster

logger = get_logger("apps.digest.summarizer")

MAX_TEXTS_PER_CLUSTER = 3
MAX_CHARS_PER_TEXT = 600

SYSTEM_PROMPT = """Ты — редактор ежедневного новостного дайджеста для одного занятого читателя.
Тебе дают кластеры постов из Telegram-каналов за последние сутки. Один кластер — одна новость;
если в кластере несколько постов, значит новость повторилась в нескольких каналах (это признак
важности).

Для каждого кластера оцени интересность по шкале 1-10:
- 9-10: крупное событие, о котором читатель точно должен узнать сегодня
- 6-8: заметная новость, полезная или любопытная
- 3-5: рутинная новость, вряд ли стоит внимания
- 1-2: реклама, розыгрыши, мемы без содержания, «вода», дубли анонсов

Ставь skip=true для рекламы, розыгрышей, подборок вакансий, чистых промо-постов и постов без
новостного содержания.

Для каждого кластера напиши:
- headline: заголовок до 10 слов, по-русски, без кликбейта
- summary: 1-2 предложения с сутью (что произошло и почему это важно), по-русски
- category: один эмодзи по теме (например 💰 🏛 🌍 🤖 ⚡️ 🎮 🧪 📱)

Пиши сжато и информативно. Не выдумывай факты, которых нет в текстах."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_id": {"type": "integer"},
                    "interest": {"type": "integer"},
                    "skip": {"type": "boolean"},
                    "category": {"type": "string"},
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["cluster_id", "interest", "skip", "category", "headline", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _cluster_block(cluster: ScoredCluster) -> str:
    channels = sorted(
        {p.channel.title or p.channel.username or str(p.channel_id) for p in cluster.posts}
    )
    texts = sorted(cluster.posts, key=lambda p: p.views or 0, reverse=True)
    lines = [
        f"### Кластер {cluster.cluster_id}",
        f"Каналов с этой новостью: {cluster.channel_count} ({', '.join(channels)})",
    ]
    for post in texts[:MAX_TEXTS_PER_CLUSTER]:
        text = post.text.strip()
        if len(text) > MAX_CHARS_PER_TEXT:
            text = text[:MAX_CHARS_PER_TEXT] + "…"
        lines.append(f"- {text}")
    return "\n".join(lines)


def summarize_clusters(clusters: list[ScoredCluster]) -> list[ScoredCluster]:
    """Rate and summarize candidate clusters in a single batched LLM call."""
    if not clusters:
        return []

    user_prompt = "\n\n".join(_cluster_block(c) for c in clusters)
    result = complete_json(SYSTEM_PROMPT, user_prompt, RESPONSE_SCHEMA)

    by_id = {c.cluster_id: c for c in clusters}
    rated = 0
    for item in result.get("items", []):
        cluster = by_id.get(item["cluster_id"])
        if cluster is None:
            continue
        cluster.llm_interest = max(1, min(10, int(item["interest"])))
        cluster.llm_skip = bool(item["skip"])
        cluster.category = item["category"].strip()
        cluster.headline = item["headline"].strip()
        cluster.summary = item["summary"].strip()
        rated += 1

    logger.info("clusters summarized", extra={"sent": len(clusters), "rated": rated})
    return [c for c in clusters if c.llm_interest is not None]
