"""
다음 뉴스 발견 어댑터.

전략:
  search.daum.net/search?w=news&sort=recency&period=d&p=N 으로 풀 HTML 반복 요청.
  - p 파라미터로 페이지네이션 (1, 2, 3, ...)
  - SHOW_DNS 쿠키: 0=전체(기본), 1=뉴스제휴 언론사만. DAUM_NEWS_ALL 환경변수로 제어.
  - 기사 링크 두 종류:
      v.daum.net/v/{id}              — 제휴 언론사 (Daum 뷰어)
      cp.news.search.daum.net/p/{id} — 비제휴 언론사 (리다이렉트 → 실제 기사)
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
            client.cookies.set("SHOW_DNS", "0" if config.DAUM_NEWS_ALL else "1", domain="search.daum.net")
            resp = client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()

        urls = _parse_urls(resp.text)
        has_more    = len(urls) >= 10 and page < self._max_pages
        next_cursor = str(page + 1) if has_more else None

        return DiscoverResult(urls=urls, next_cursor=next_cursor, has_more=has_more)


def _parse_urls(html: str) -> list[str]:
    """a.tit_main 제목 링크에서 기사 URL 추출. v.daum 추적 파라미터(?f=o) 제거."""
    tree = HTMLParser(html)
    seen: dict[str, None] = {}

    for node in tree.css("a.tit_main[href]"):
        href = node.attributes.get("href", "")
        if not href:
            continue
        if "v.daum.net/v/" in href:
            seen[href.split("?")[0]] = None
        elif "cp.news.search.daum.net/p/" in href:
            seen[href] = None

    return list(seen)
