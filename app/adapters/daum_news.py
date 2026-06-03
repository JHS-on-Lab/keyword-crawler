"""
다음 뉴스 발견 어댑터.

전략:
  search.daum.net/search?w=news&sort=recency&period=d&p=N 으로 풀 HTML 반복 요청.
  - p 파라미터로 페이지네이션 (1, 2, 3, ...)
  - 기사 링크: v.daum.net/v/{id} 패턴 (Daum 뷰어)
  - period 파라미터: d=1일, w=1주, m=1개월

커서: 페이지 번호 (1→2→3→...). None이면 첫 페이지.
"""

from __future__ import annotations

from selectolax.parser import HTMLParser

from app import config
from app.adapters._base import PaginatedAdapter
from app.fetch._client import make_client
from app.types import DiscoverResult, PortalType

_SEARCH_URL = "https://search.daum.net/search"

# period 파라미터: d=1일, w=1주, m=1개월
_DEFAULT_PERIOD   = "d"
_DEFAULT_DELAY_MS = 800


class DaumNewsAdapter(PaginatedAdapter):
    portal_type: str = PortalType.DAUM_NEWS

    def __init__(
        self,
        period: str    = _DEFAULT_PERIOD,
        max_pages: int | None = None,
        delay_ms: int  = _DEFAULT_DELAY_MS,
    ) -> None:
        super().__init__(period, max_pages or config.DAUM_MAX_PAGES, delay_ms)

    def discover(self, keyword: str, cursor: str | None) -> DiscoverResult:
        page = int(cursor) if cursor else 1

        if result := self._exceeded(page):
            return result

        self._delay(is_first=(page == 1))

        params = {
            "w":      "news",
            "q":      keyword,
            "sort":   "recency",
            "period": self._period,
            "p":      str(page),
        }

        with make_client(referer="https://www.daum.net/") as client:
            resp = client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()

        urls = _parse_urls(resp.text)
        has_more    = len(urls) >= 10 and page < self._max_pages
        next_cursor = str(page + 1) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)


def _parse_urls(html: str) -> list[str]:
    """
    v.daum.net/v/{id} 패턴 기사 링크 추출.
    각 기사는 썸네일·제목·요약 3개의 <a> 태그가 같은 href를 가지므로 중복 제거.
    class='' 인 것이 제목 링크 (텍스트 있음).
    """
    tree = HTMLParser(html)
    seen: dict[str, None] = {}

    for node in tree.css('a[href*="v.daum.net/v/"]'):
        if node.attributes.get("class", "") != "":
            continue          # 썸네일(thumb_bf) 제외
        href = node.attributes.get("href", "")
        if href:
            seen[href] = None

    return list(seen)
