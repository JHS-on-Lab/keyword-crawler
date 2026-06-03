"""웨이보 발견 어댑터 (전략 미확정 — 구현 전 decisions/weibo-discovery.md 먼저 작성)."""

from __future__ import annotations

from app.types import DiscoverResult, PortalType


class WeiboAdapter:
    portal_type: str = PortalType.WEIBO

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        raise NotImplementedError
