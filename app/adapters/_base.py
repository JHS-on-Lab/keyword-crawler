"""
페이지 단위로 검색 결과를 가져오는 어댑터의 공통 베이스.

NaverNewsAdapter 와 DaumNewsAdapter 가 중복으로 갖고 있던
  - period / max_pages / delay_ms 초기화
  - 페이지 한도 체크
  - 페이지 간 딜레이
를 한 곳으로 모았다.
"""

from __future__ import annotations

import time

from app.types import DiscoverResult


class PaginatedAdapter:
    """max_pages / delay_ms 를 가지는 어댑터의 공통 베이스."""

    def __init__(self, period: str, max_pages: int, delay_ms: int) -> None:
        self._period    = period
        self._max_pages = max_pages
        self._delay_ms  = delay_ms

    def _exceeded(self, page_num: int) -> DiscoverResult | None:
        """max_pages 초과 시 빈 결과 반환, 아니면 None."""
        if page_num > self._max_pages:
            return DiscoverResult(urls=[], next_cursor=None, has_more=False)
        return None

    def _delay(self, is_first: bool) -> None:
        """첫 페이지가 아닐 때 딜레이를 적용한다."""
        if not is_first:
            time.sleep(self._delay_ms / 1000)
