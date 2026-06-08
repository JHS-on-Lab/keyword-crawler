"""
발견(Discovery) 단계 수동 실행 스크립트.

사용법:
  # 특정 키워드로 직접 실행 (DB 스케줄 무시, URL만 출력)
  python scripts/run_discovery.py --portal naver_news --keyword 삼성전자 --dry-run

  # 특정 키워드로 직접 실행 + DB 저장
  python scripts/run_discovery.py --portal naver_news --keyword 삼성전자

  # DB 에서 다음 due 키워드를 하나 꺼내 발견 실행
  python scripts/run_discovery.py --portal naver_news

  # DB 에서 꺼내되 URL만 출력 (next_discover_at 등 DB 변경 없음)
  python scripts/run_discovery.py --portal naver_news --dry-run

  # 최대 페이지 수 지정
  python scripts/run_discovery.py --portal naver_news --keyword 삼성전자 --max-pages 2
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import config

_PORTALS = ("naver_news", "daum_news", "google_news", "baidu_news", "naver_stock")
KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="발견 단계 수동 실행")
    p.add_argument("--portal",    required=True, choices=_PORTALS, help="실행할 포털")
    p.add_argument("--keyword",   default=None,  help="직접 지정 키워드 (생략 시 DB 에서 꺼냄)")
    p.add_argument("--max-pages", type=int, default=None, help="최대 페이지 수 (어댑터 기본값 사용)")
    p.add_argument("--dry-run",   action="store_true", help="DB 에 쓰지 않고 URL 만 출력")
    p.add_argument("--worker-id", default="script", help="워커 식별자 (기본: script)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# 어댑터 팩토리
# ---------------------------------------------------------------------------

def _make_adapter(portal: str, max_pages: int | None):
    pt = portal.upper()
    kwargs = {"max_pages": max_pages} if max_pages else {}

    if pt == "NAVER_NEWS":
        from app.adapters.naver_news import NaverNewsAdapter
        return NaverNewsAdapter(**kwargs)
    if pt == "DAUM_NEWS":
        from app.adapters.daum_news import DaumNewsAdapter
        return DaumNewsAdapter(**kwargs)
    if pt == "NAVER_STOCK":
        from app.adapters.naver_stock import NaverStockAdapter
        return NaverStockAdapter(**kwargs)
    if pt == "GOOGLE_NEWS":
        from app.adapters.google_news import UCGoogleNewsAdapter
        return UCGoogleNewsAdapter()
    if pt == "BAIDU_NEWS":
        from app.adapters.baidu_news import BaiduNewsAdapter
        return BaiduNewsAdapter()
    raise ValueError(f"지원하지 않는 portal: {portal}")


# ---------------------------------------------------------------------------
# 공통 수집 루프
# ---------------------------------------------------------------------------

def _discover_all(adapter, keyword: str) -> tuple[list[str], str | None]:
    """모든 페이지를 순회해 URL 을 수집하고 페이지별 결과를 출력한다."""
    all_urls: list[str] = []
    cursor = None
    page   = 1

    while True:
        result = adapter.discover(keyword, cursor)
        print(f"  p{page}: found={len(result.urls)}")
        for url in result.urls:
            print(f"    {url}")
        all_urls.extend(result.urls)

        if not result.has_more:
            break
        cursor, page = result.next_cursor, page + 1

    return all_urls, None  # 정상 완료 → 재개 cursor 불필요


# ---------------------------------------------------------------------------
# --keyword 직접 지정 모드
# ---------------------------------------------------------------------------

def _run_keyword_mode(args: argparse.Namespace) -> None:
    """DB 스케줄을 거치지 않고 키워드를 직접 지정해 발견을 실행한다."""
    from sqlalchemy import text
    from app.repository.db import db_context
    from app.repository.article_url_repo import ArticleUrlRepo

    dry = args.dry_run

    # 수집 전에 keyword 테이블 존재 여부 확인 — 미등록이면 중단
    with db_context() as engine:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM t_keyword WHERE keyword = :kw AND portal_type = :pt"),
                {"kw": args.keyword, "pt": args.portal.upper()},
            ).fetchone()

    if row is None:
        print(f"오류: '{args.keyword}' (portal={args.portal.upper()}) 가 t_keyword 테이블에 없습니다. 수집을 중단합니다.")
        sys.exit(1)

    keyword_id = row[0]
    print(f"[portal={args.portal}] keyword='{args.keyword}' (id={keyword_id}) 발견 시작"
          + (" (dry-run)" if dry else ""))

    adapter = _make_adapter(args.portal, args.max_pages)
    mono_start = time.monotonic()

    urls, _ = _discover_all(adapter, args.keyword)
    duration_ms = int((time.monotonic() - mono_start) * 1000)

    print(f"\n총 {len(urls)}개 URL 발견 ({duration_ms}ms)")

    if dry:
        return

    with db_context() as engine:
        ins, skp = ArticleUrlRepo(engine).bulk_insert_discovered(
            urls, keyword_id=keyword_id, portal_type=args.portal.upper()
        )
    print(f"DB 저장: inserted={ins} skipped={skp}")


# ---------------------------------------------------------------------------
# DB 모드 (due 키워드 자동 선택)
# ---------------------------------------------------------------------------

def _peek_next_keyword(engine, portal: str) -> dict | None:
    """due 키워드를 점유 없이 조회한다 (dry-run 전용, DB 변경 없음)."""
    from sqlalchemy import text
    portal_filter = "" if portal.upper() == "ALL" else "AND portal_type = :portal"
    with engine.connect() as conn:
        row = conn.execute(
            text(f"""
                SELECT id, keyword, portal_type, retry_pending
                FROM t_keyword
                WHERE enabled = true
                  AND (next_discover_at IS NULL OR next_discover_at <= NOW())
                  {portal_filter}
                ORDER BY priority DESC, next_discover_at ASC
                LIMIT 1
            """),
            {"portal": portal.upper()},
        ).fetchone()
    return dict(row._mapping) if row else None


def _run_db_mode(args: argparse.Namespace) -> None:
    """DB 에서 다음 due 키워드를 꺼내 발견을 실행한다."""
    from app.repository.db import db_context
    from app.repository.keyword_repo import KeywordRepo
    from app.repository.article_url_repo import ArticleUrlRepo
    from app.repository.collection_log_repo import CollectionLogRepo, DiscoveryLog

    dry = args.dry_run

    with db_context() as engine:
        # dry-run 시 점유(claim) 없이 조회만 — next_discover_at 변경 없음
        if dry:
            kw = _peek_next_keyword(engine, args.portal)
        else:
            kw_repo = KeywordRepo(engine)
            kw = kw_repo.claim_next(portal=args.portal, worker_id=args.worker_id)

        if kw is None:
            print(f"[portal={args.portal}] 수집할 due 키워드 없음")
            return

        keyword     = kw["keyword"]
        keyword_id  = kw["id"]
        portal_type = kw["portal_type"]
        is_retry = bool(kw.get("retry_pending"))

        print(f"[portal={portal_type}] keyword='{keyword}' (id={keyword_id}) 발견 시작"
              + (" (dry-run)" if dry else "")
              + (" (retry: full scan from page 1)" if is_retry else ""))

        if not dry:
            kw_repo   = KeywordRepo(engine)
            url_repo  = ArticleUrlRepo(engine)
            log_repo  = CollectionLogRepo(engine)

        adapter    = _make_adapter(portal_type, args.max_pages)
        started_at = datetime.now(KST)
        mono_start = time.monotonic()

        try:
            urls, _ = _discover_all(adapter, keyword)  # 재시도 포함 항상 1페이지부터 full scan
            duration_ms = int((time.monotonic() - mono_start) * 1000)

            print(f"\n총 {len(urls)}개 URL 발견 ({duration_ms}ms)")

            if dry:
                return

            ins, skp = url_repo.bulk_insert_discovered(urls, keyword_id, portal_type)
            print(f"DB 저장: inserted={ins} skipped={skp}")

            kw_repo.set_retry_pending(keyword_id, False)

            log_repo.insert_discovery(DiscoveryLog(
                keyword_id    = keyword_id,
                portal_type   = portal_type,
                worker_id     = args.worker_id,
                started_at    = started_at,
                duration_ms   = duration_ms,
                urls_found    = len(urls),
                urls_inserted = ins,
                urls_skipped  = skp,
            ))

        except Exception as exc:
            duration_ms = int((time.monotonic() - mono_start) * 1000)
            print(f"\n오류 ({duration_ms}ms): {exc}", file=sys.stderr)
            if not dry:
                kw_repo.set_retry_pending(keyword_id, True)
            raise


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    # dry-run 이 아닐 때만 DB 연결 정보 검증
    if not args.dry_run:
        config.validate()

    if args.keyword:
        _run_keyword_mode(args)
    else:
        _run_db_mode(args)


if __name__ == "__main__":
    main()
