from __future__ import annotations

from datetime import datetime

import httpx

from apps.collectors.base import PollingCollector, RawItem
from apps.common.config import get_config
from apps.common.logging import get_logger
from apps.pipeline.normalize import strip_html

logger = get_logger("apps.collectors.freelancehunt")

API_URL = "https://api.freelancehunt.com/v2/projects"


def _parse_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def project_to_item(project: dict) -> RawItem | None:
    project_id = project.get("id")
    attrs = project.get("attributes") or {}
    name = (attrs.get("name") or "").strip()
    if project_id is None or not name:
        return None

    parts = [name]
    description = attrs.get("description_html") or attrs.get("description") or ""
    if description:
        parts.append(strip_html(description).strip())
    budget = attrs.get("budget") or {}
    if budget.get("amount"):
        parts.append(f"Бюджет: {budget['amount']} {budget.get('currency', '')}".strip())

    employer = attrs.get("employer") or {}
    author_name = " ".join(
        part for part in (employer.get("first_name"), employer.get("last_name")) if part
    ) or None

    url = ((project.get("links") or {}).get("self") or {}).get("web")

    return RawItem(
        external_id=str(project_id),
        text="\n\n".join(parts),
        url=url,
        author_name=author_name,
        author_username=employer.get("login"),
        author_id=employer.get("id"),
        published_at=_parse_datetime(attrs.get("published_at")),
    )


class FreelanceHuntCollector(PollingCollector):
    """Опрос первой страницы проектов FreelanceHunt API v2."""

    async def poll(self, source_id: int, config: dict, state: dict) -> list[RawItem]:
        token = get_config().freelancehunt_token
        if not token:
            raise RuntimeError("FREELANCEHUNT_TOKEN is not set")

        params = {}
        skill_ids = config.get("skill_ids")
        if skill_ids:
            params["filter[skill_id]"] = ",".join(str(s) for s in skill_ids)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                API_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()

        items = []
        for project in payload.get("data", []):
            item = project_to_item(project)
            if item is not None:
                items.append(item)
        logger.debug("freelancehunt poll done", extra={"source_id": source_id, "count": len(items)})
        return items
