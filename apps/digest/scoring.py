from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.common.models import ChannelPost

ENGAGEMENT_CAP = 5.0
REPETITION_WEIGHT = 2.0
ENGAGEMENT_WEIGHT = 1.0
RECENCY_WEIGHT = 0.5
MEDIA_BONUS = 0.2
MEDIAN_LOOKBACK_DAYS = 14


@dataclass
class ScoredCluster:
    cluster_id: int
    posts: list[ChannelPost]
    prescore: float
    repetition_score: float
    engagement_score: float
    llm_interest: int | None = None
    llm_skip: bool = False
    category: str = ""
    headline: str = ""
    summary: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def channel_count(self) -> int:
        return len({p.channel_id for p in self.posts})

    @property
    def primary_post(self) -> ChannelPost:
        # Post to link to: the one with the most views, fallback to the earliest.
        return max(self.posts, key=lambda p: ((p.views or 0), -p.posted_at.timestamp()))

    def final_score(self) -> float:
        interest = self.llm_interest or 0
        return interest + REPETITION_WEIGHT * self.repetition_score + self.engagement_score


def channel_median_views(session: Session, channel_id: int) -> float:
    since = datetime.now(timezone.utc) - timedelta(days=MEDIAN_LOOKBACK_DAYS)
    views = session.scalars(
        select(ChannelPost.views).where(
            ChannelPost.channel_id == channel_id,
            ChannelPost.posted_at >= since,
            ChannelPost.views.isnot(None),
        )
    ).all()
    if not views:
        return 0.0
    return float(statistics.median(views))


def _engagement_ratio(post: ChannelPost, medians: dict[int, float]) -> float:
    median = medians.get(post.channel_id, 0.0)
    if not median or post.views is None:
        return 1.0
    return min(post.views / median, ENGAGEMENT_CAP)


def _as_utc(dt: datetime) -> datetime:
    # SQLite (tests) returns naive datetimes; Postgres returns aware ones.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _recency_score(posts: list[ChannelPost], now: datetime, window_hours: int) -> float:
    newest = max(_as_utc(p.posted_at) for p in posts)
    age_hours = max((now - newest).total_seconds() / 3600, 0.0)
    return max(1.0 - age_hours / window_hours, 0.0)


def score_clusters(
    session: Session,
    clusters: list[list[ChannelPost]],
    window_hours: int,
) -> list[ScoredCluster]:
    now = datetime.now(timezone.utc)
    channel_ids = {p.channel_id for cluster in clusters for p in cluster}
    medians = {cid: channel_median_views(session, cid) for cid in channel_ids}

    scored: list[ScoredCluster] = []
    for idx, posts in enumerate(clusters):
        # Repetition across channels is the strongest signal: log2 keeps it sane.
        repetition = math.log2(1 + len({p.channel_id for p in posts}))
        engagement = max(_engagement_ratio(p, medians) for p in posts) / ENGAGEMENT_CAP
        recency = _recency_score(posts, now, window_hours)
        media = MEDIA_BONUS if any(p.has_media for p in posts) else 0.0

        prescore = (
            REPETITION_WEIGHT * repetition
            + ENGAGEMENT_WEIGHT * engagement
            + RECENCY_WEIGHT * recency
            + media
        )
        scored.append(
            ScoredCluster(
                cluster_id=idx,
                posts=posts,
                prescore=prescore,
                repetition_score=repetition,
                engagement_score=engagement,
            )
        )

    scored.sort(key=lambda c: c.prescore, reverse=True)
    return scored
