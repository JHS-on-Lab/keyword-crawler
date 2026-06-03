"""어댑터 팩토리 — portal_type 문자열로 SourceAdapter 구현체를 반환."""

from __future__ import annotations

from app.ports import SourceAdapter


def make_adapter(portal_type: str) -> SourceAdapter:
    pt = portal_type.upper()
    if pt == "NAVER_NEWS":
        from app.adapters.naver_news import NaverNewsAdapter
        return NaverNewsAdapter()
    if pt == "DAUM_NEWS":
        from app.adapters.daum_news import DaumNewsAdapter
        return DaumNewsAdapter()
    if pt == "GOOGLE_NEWS":
        from app.adapters.google_news import UCGoogleNewsAdapter
        return UCGoogleNewsAdapter()
    if pt == "WEIBO":
        from app.adapters.weibo import WeiboAdapter
        return WeiboAdapter()
    if pt == "NAVER_STOCK":
        from app.adapters.naver_stock import NaverStockAdapter
        return NaverStockAdapter()
    raise ValueError(f"알 수 없는 portal_type: {portal_type}")
