from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telethon import TelegramClient

from apps.common.config import get_config
from apps.common.db import get_session
from apps.common.logging import get_logger
from apps.common.models import ChannelPost, Digest
from apps.digest.clustering import cluster_posts
from apps.digest.scoring import ScoredCluster, score_clusters
from apps.digest.summarizer import summarize_clusters

logger = get_logger("apps.digest.builder")

MIN_INTEREST = 4
TELEGRAM_MESSAGE_LIMIT = 4000


def _post_link(post: ChannelPost) -> str:
    username = post.channel.username
    if username:
        return f"https://t.me/{username}/{post.tg_message_id}"
    # Private channels: t.me/c/ links use the internal id (without the -100 prefix).
    internal_id = str(post.channel_id).removeprefix("-100")
    return f"https://t.me/c/{internal_id}/{post.tg_message_id}"


def _format_item(index: int, cluster: ScoredCluster) -> str:
    post = cluster.primary_post
    channel_name = post.channel.title or post.channel.username or str(post.channel_id)
    line = f"{index}. {cluster.category} **{cluster.headline}**\n{cluster.summary}"
    line += f"\n↳ [{channel_name}]({_post_link(post)})"
    if cluster.channel_count > 1:
        line += f" +{cluster.channel_count - 1} кан."
    return line


def _format_digest(digest_date: date, clusters: list[ScoredCluster]) -> str:
    header = f"📰 **Дайджест за {digest_date.strftime('%d.%m.%Y')}**"
    items = [_format_item(i + 1, c) for i, c in enumerate(clusters)]
    return "\n\n".join([header, *items])


def build_digest(digest_date: date | None = None) -> Digest | None:
    """Cluster → score → LLM summarize → format. Returns the stored digest."""
    config = get_config()
    digest_date = digest_date or datetime.now(timezone.utc).date()
    since = datetime.now(timezone.utc) - timedelta(hours=config.digest_window_hours)

    with get_session() as session:
        posts = (
            session.scalars(
                select(ChannelPost)
                .options(joinedload(ChannelPost.channel))
                .where(ChannelPost.posted_at >= since, ChannelPost.digest_id.is_(None))
            )
            .unique()
            .all()
        )

        if not posts:
            logger.info("no fresh posts, digest skipped")
            return None

        clusters = cluster_posts(posts)
        scored = score_clusters(session, clusters, config.digest_window_hours)
        candidates = scored[: config.digest_llm_candidates]
        logger.info(
            "clusters prepared",
            extra={"posts": len(posts), "clusters": len(scored), "candidates": len(candidates)},
        )

        rated = summarize_clusters(candidates)
        selected = [c for c in rated if not c.llm_skip and (c.llm_interest or 0) >= MIN_INTEREST]
        selected.sort(key=lambda c: c.final_score(), reverse=True)
        selected = selected[: config.digest_max_items]

        if not selected:
            logger.info("nothing interesting enough, digest skipped")
            return None

        text = _format_digest(digest_date, selected)
        items_json = [
            {
                "headline": c.headline,
                "summary": c.summary,
                "category": c.category,
                "interest": c.llm_interest,
                "channels": c.channel_count,
                "link": _post_link(c.primary_post),
                "final_score": round(c.final_score(), 2),
            }
            for c in selected
        ]

        digest = Digest(digest_date=digest_date, text=text, items_json=items_json)
        session.add(digest)
        session.flush()
        for cluster in candidates:
            for post in cluster.posts:
                post.digest_id = digest.id

        logger.info("digest built", extra={"digest_id": str(digest.id), "items": len(selected)})
        return digest


def _split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit and current:
            parts.append(current)
            current = block
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


async def send_digest(client: TelegramClient, digest_id) -> None:
    config = get_config()
    with get_session() as session:
        digest = session.get(Digest, digest_id)
        if digest is None:
            raise ValueError(f"digest {digest_id} not found")
        text = digest.text

    target = config.digest_target_chat
    entity = "me" if target == "me" else await _resolve_target(client, target)
    for part in _split_message(text):
        await client.send_message(entity, part, parse_mode="md", link_preview=False)

    with get_session() as session:
        digest = session.get(Digest, digest_id)
        digest.sent_at = datetime.now(timezone.utc)

    logger.info("digest sent", extra={"digest_id": str(digest_id), "target": target})


async def _resolve_target(client: TelegramClient, target: str):
    if target.lstrip("-").isdigit():
        return await client.get_entity(int(target))
    return await client.get_entity(target)
