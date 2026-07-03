from __future__ import annotations

import re

from apps.common.models import ChannelPost

_URL_RE = re.compile(r"https?://\S+")
_NON_WORD_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")

SHINGLE_SIZE = 3
SHINGLE_THRESHOLD = 0.35  # verbatim reposts / forwards
STEM_THRESHOLD = 0.5  # paraphrased coverage of the same news
STEM_LENGTH = 6

# Frequent Russian/English function words that inflate similarity between unrelated news.
STOPWORDS = frozenset(
    """
    и в на с по не что это для как из у о за к от до же бы а но или под над при
    его ее их мы вы он она они оно то так вот еще уже том все всех этой этот эта
    также чтобы если когда где через после перед между был была были будет
    the a an of to in on for and or is are was were be been with at by from as
    """.split()
)


def normalize_text(text: str) -> str:
    text = _URL_RE.sub(" ", text.lower())
    text = _NON_WORD_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _words(text: str) -> list[str]:
    return normalize_text(text).split()


def shingles(text: str, size: int = SHINGLE_SIZE) -> frozenset[str]:
    words = _words(text)
    if len(words) < size:
        return frozenset(words)
    return frozenset(" ".join(words[i : i + size]) for i in range(len(words) - size + 1))


def stems(text: str) -> frozenset[str]:
    """Crude language-agnostic stemming: drop stopwords, truncate inflections."""
    return frozenset(w[:STEM_LENGTH] for w in _words(text) if w not in STOPWORDS)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return intersection / (len(a) + len(b) - intersection)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def same_news(
    shingles_a: frozenset[str],
    shingles_b: frozenset[str],
    stems_a: frozenset[str],
    stems_b: frozenset[str],
) -> bool:
    # Two signals: near-verbatim overlap (forwards) or shared vocabulary (paraphrases).
    if jaccard(shingles_a, shingles_b) >= SHINGLE_THRESHOLD:
        return True
    return jaccard(stems_a, stems_b) >= STEM_THRESHOLD


def cluster_posts(posts: list[ChannelPost]) -> list[list[ChannelPost]]:
    """Group posts about the same news: the same story reposted or paraphrased by
    several channels lands in one cluster. Cluster size is the main
    interestingness signal."""
    post_shingles = [shingles(p.text) for p in posts]
    post_stems = [stems(p.text) for p in posts]
    uf = _UnionFind(len(posts))

    for i in range(len(posts)):
        if not post_stems[i]:
            continue
        for j in range(i + 1, len(posts)):
            if not post_stems[j]:
                continue
            if same_news(post_shingles[i], post_shingles[j], post_stems[i], post_stems[j]):
                uf.union(i, j)

    groups: dict[int, list[ChannelPost]] = {}
    for i, post in enumerate(posts):
        groups.setdefault(uf.find(i), []).append(post)
    return list(groups.values())
