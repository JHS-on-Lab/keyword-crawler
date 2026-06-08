"""
추출(Extraction) 단계 수동 실행 스크립트.

사용법:
  # 특정 URL 추출 테스트 — 파일 미저장, 결과만 출력
  python scripts/run_extraction.py --url "https://finance.naver.com/item/board_read.naver?code=000660&nid=421731371" --dry-run

  # 특정 URL 추출 + 파일 저장
  python scripts/run_extraction.py --url "https://..." --portal NAVER_STOCK --keyword 000660

  # DB 에서 discovered URL 하나 꺼내 추출
  python scripts/run_extraction.py

  # 특정 포털 URL 만 꺼내 추출
  python scripts/run_extraction.py --portal NAVER_NEWS
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import config


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="추출 단계 수동 실행")
    p.add_argument("--url",      default=None, help="직접 지정 URL (생략 시 DB 에서 꺼냄)")
    p.add_argument("--portal",   default=None, help="포털 타입 (예: NAVER_STOCK)")
    p.add_argument("--keyword",  default="",   help="키워드 컨텍스트 (기본: 빈 문자열)")
    p.add_argument("--dry-run",  action="store_true", help="파일 미저장, 결과만 출력")
    p.add_argument("--worker-id", default="script", help="워커 식별자 (기본: script)")
    return p.parse_args()


def _make_components(dry_run: bool):
    """추출에 필요한 컴포넌트를 생성해 반환한다."""
    from app.extraction.extractor import DefaultExtractor
    from app.fetch.headless import HeadlessFetcher
    from app.fetch.http_client import HttpFetcher
    from app.fetch.rate_limit import RateLimiter
    from app.repository.db import db_context
    from app.repository.domain_repo import DomainRepo
    from app.sink import make_sink
    from app.sink.file_sink import FileSink

    engine_ctx = db_context()
    engine = engine_ctx.__enter__()

    domain_repo = DomainRepo(engine)
    fetcher     = HttpFetcher()
    headless    = HeadlessFetcher()
    limiter     = RateLimiter(domain_repo)
    extractor   = DefaultExtractor(domain_repo=domain_repo)
    sink        = FileSink() if not dry_run else None

    return engine_ctx, engine, domain_repo, fetcher, headless, limiter, extractor, sink


def _run_url_mode(args: argparse.Namespace) -> None:
    """URL 직접 지정 모드."""
    from app.fetch.headless import fetch_by_render_mode
    from app.types import Article, ExtractionFailure, RenderMode
    import dataclasses, json

    url  = args.url
    host = urlparse(url).netloc

    print(f"URL    : {url}")
    print(f"host   : {host}")
    print(f"portal : {args.portal or '(미지정)'}")
    print(f"keyword: {args.keyword or '(없음)'}")
    print(f"mode   : {'dry-run' if args.dry_run else '파일 저장'}\n")

    if not args.dry_run:
        config.validate()

    (engine_ctx, engine,
     domain_repo, fetcher, headless,
     limiter, extractor, sink) = _make_components(args.dry_run)

    try:
        domain = domain_repo.get(host)
        render_mode = (domain or {}).get("render_mode", RenderMode.STATIC)
        print(f"render_mode : {render_mode}")
        wait_for_selector = None
        if domain and domain.get("rules_json"):
            import json as _json
            rules = domain["rules_json"]
            if isinstance(rules, str):
                rules = _json.loads(rules)
            rule_type = next((t for t in ("json_api", "amp_url", "next_data") if t in rules), "css/xpath")
            wait_for_selector = rules.get("headless_wait_for")
            print(f"domain rule : {rule_type}\n")
        else:
            print("domain rule : 없음 (라이브러리 체인)\n")

        limiter.wait(host)

        print("=== Fetch ===")
        fr = fetch_by_render_mode(url, render_mode, fetcher, headless,
                                  wait_for_selector=wait_for_selector)
        print(f"status : {fr.status_code}")
        print(f"html   : {len(fr.html):,} bytes\n")

        if fr.status_code >= 400:
            print(f"오류: HTTP {fr.status_code}")
            return

        print("=== Extract ===")
        result = extractor.extract(
            url=fr.url,
            html=fr.html,
            host=host,
            portal_type=args.portal or "",
            keyword=args.keyword,
        )

        if isinstance(result, ExtractionFailure):
            print(f"실패: [{result.error_code.value}] {result.error_msg}")
            print(f"      permanent={result.is_permanent}")
            return

        print(f"method      : {result.extraction_method}")
        print(f"title       : {result.title}")
        print(f"author      : {result.author}")

        print(f"published_at: {result.published_at}")
        print(f"body_len    : {result.body_len}")
        print(f"body:\n{result.body}")

        if args.dry_run:
            print("\n(dry-run — 파일 미저장)")
            return

        print("\n=== Sink ===")
        sink.write(result)
        print(f"저장 완료: {config.FILE_SINK_DIR}")

    finally:
        headless.close()
        engine_ctx.__exit__(None, None, None)


def _run_db_mode(args: argparse.Namespace) -> None:
    """DB 에서 discovered URL 하나를 꺼내 추출한다."""
    from app.fetch.headless import fetch_by_render_mode
    from app.repository.article_url_repo import ArticleUrlRepo
    from app.types import ExtractionFailure, RenderMode

    config.validate()

    (engine_ctx, engine,
     domain_repo, fetcher, headless,
     limiter, extractor, sink) = _make_components(args.dry_run)

    try:
        url_repo = ArticleUrlRepo(engine)
        portal_filter = args.portal.upper() if args.portal else None
        item = url_repo.claim_next(worker_id=args.worker_id, portal=portal_filter)

        if item is None:
            print(f"처리할 discovered URL 없음 (portal={args.portal or 'all'})")
            return

        url     = item["url"]
        host    = item["host"]
        portal  = item["portal_type"]
        keyword = item.get("keyword", "")

        print(f"URL    : {url}")
        print(f"host   : {host}")
        print(f"portal : {portal}")
        print(f"id     : {item['id']}\n")

        domain = domain_repo.get(host)
        render_mode = (domain or {}).get("render_mode", RenderMode.STATIC)

        limiter.wait(host)

        print("=== Fetch ===")
        try:
            fr = fetch_by_render_mode(url, render_mode, fetcher, headless)
        except Exception as exc:
            print(f"fetch 오류: {exc}")
            from app.types import ErrorCode
            url_repo.mark_failed(item["id"], error_code=ErrorCode.UNKNOWN,
                                 error_msg=str(exc), is_permanent=False,
                                 next_retry_at=None)
            return

        print(f"status : {fr.status_code}")
        print(f"html   : {len(fr.html):,} bytes\n")

        if fr.status_code >= 400:
            print(f"오류: HTTP {fr.status_code}")
            return

        print("=== Extract ===")
        result = extractor.extract(
            url=fr.url, html=fr.html, host=host,
            portal_type=portal, keyword=keyword,
        )

        if isinstance(result, ExtractionFailure):
            print(f"실패: [{result.error_code.value}] {result.error_msg}")
            url_repo.mark_failed(item["id"], error_code=result.error_code,
                                 error_msg=result.error_msg,
                                 is_permanent=result.is_permanent,
                                 next_retry_at=None)
            return

        print(f"method      : {result.extraction_method}")
        print(f"title       : {result.title}")
        print(f"author      : {result.author}")

        print(f"published_at: {result.published_at}")
        print(f"body_len    : {result.body_len}")
        print(f"body:\n{result.body}")

        if args.dry_run:
            print("\n(dry-run — 파일 미저장, DB 상태 미변경)")
            return

        print("\n=== Sink ===")
        sink.write(result)
        url_repo.mark_stored(item["id"], extraction_method=result.extraction_method)
        domain_repo.upsert_health(host, success=True, body_len=result.body_len)
        print("저장 완료.")

    finally:
        headless.close()
        engine_ctx.__exit__(None, None, None)


def main() -> None:
    args = _parse_args()

    if args.url:
        _run_url_mode(args)
    else:
        _run_db_mode(args)


if __name__ == "__main__":
    main()
