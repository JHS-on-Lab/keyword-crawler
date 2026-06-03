"""
추출 워커: article_url 테이블에서 URL 을 꺼내 본문을 스크랩하고 파일로 저장한다.

한 URL 의 처리 순서:
  1. claim_next()  — DB 에서 URL 하나를 꺼낸다 (다른 워커가 동시에 같은 URL 을 가져가지 않도록 잠금)
  2. RateLimiter   — 같은 도메인에 너무 빨리 요청하지 않도록 대기
  3. HttpFetcher   — URL 의 HTML 을 내려받는다
  4. Extractor     — HTML 에서 제목·본문을 추출한다
  5. Sink          — 결과를 저장한다 (FileSink: JSONL, SolrSink: Solr)
  6. mark_stored / mark_failed / mark_dead — 처리 결과를 DB 에 기록한다

실패 처리:
  - 일시적 오류(네트워크 장애, 서버 500 등) → failed_transient 로 표시, 나중에 자동 재시도
  - 영구 오류(404, 페이월 등)               → failed_permanent 로 표시, 재시도 안 함
  - MAX_ATTEMPTS 초과                       → dead 로 표시

URL 이 없으면 10초 쉬었다가 다시 확인한다. 수동 개입 없이 계속 돌아간다.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta

from app import config
from app.worker import _healthcheck
from app.domain_logic.backoff import next_retry_at
from app.domain_logic.failure_classifier import classify_http, classify_exception
from app.extraction.extractor import DefaultExtractor
from app.fetch.headless import HeadlessFetcher, fetch_by_render_mode
from app.fetch.http_client import HttpFetcher
from app.fetch.rate_limit import RateLimiter
from app.repository.article_url_repo import ArticleUrlRepo
from app.repository.collection_log_repo import CollectionLogRepo, ExtractionLog
from app.repository.db import db_context
from app.repository.domain_repo import DomainRepo
from app.sink import make_sink
from app.ports import Sink
from app.types import ErrorCode, ExtractionFailure, RenderMode

logger = logging.getLogger(__name__)

KST        = timezone(timedelta(hours=9))
_IDLE_SEC  = 10
_ERROR_SEC = 5


def run_extraction_loop(portal: str, worker_id: str) -> None:
    """추출 워커 메인 루프. __main__.py 에서 호출."""
    logger.info(
        "extraction loop started",
        extra={"phase": "startup", "worker_id": worker_id, "component": "extractor"},
    )

    # HeadlessFetcher 는 브라우저 프로세스를 띄우므로 루프 밖에서 한 번만 생성한다.
    headless_fetcher = HeadlessFetcher()

    with db_context() as engine:
        url_repo    = ArticleUrlRepo(engine)
        log_repo    = CollectionLogRepo(engine)
        domain_repo = DomainRepo(engine)
        fetcher     = HttpFetcher()
        limiter     = RateLimiter(domain_repo)
        extractor   = DefaultExtractor(domain_repo=domain_repo)  # domain_repo 주입 → 규칙 엔진 활성화
        sink        = make_sink()  # SINK_TYPE 환경변수로 file / solr 선택

        processed = urls_success = urls_failed = 0
        heartbeat_interval  = config.HEARTBEAT_INTERVAL_SECONDS
        last_heartbeat      = time.monotonic()
        batch_start_dt      = datetime.now(KST)
        batch_start_mono    = time.monotonic()

        while True:
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                logger.info(
                    f"heartbeat processed={processed} success={urls_success} failed={urls_failed}",
                    extra={"phase": "heartbeat", "worker_id": worker_id, "component": "extractor"},
                )
                last_heartbeat = now
                _healthcheck.write()

            portal_filter = None if portal.upper() == "ALL" else portal.upper()
            try:
                item = url_repo.claim_next(worker_id=worker_id, portal=portal_filter)
            except Exception:
                logger.exception(
                    f"claim_next failed, sleeping {_ERROR_SEC}s",
                    extra={"phase": "claim", "worker_id": worker_id, "component": "extractor"},
                )
                time.sleep(_ERROR_SEC)
                continue

            if item is None:
                _flush_log(log_repo, portal, worker_id,
                           batch_start_dt, batch_start_mono,
                           processed, urls_success, urls_failed)
                processed = urls_success = urls_failed = 0
                batch_start_dt   = datetime.now(KST)
                batch_start_mono = time.monotonic()
                logger.debug(
                    f"no items, sleeping {_IDLE_SEC}s",
                    extra={"phase": "idle", "worker_id": worker_id, "component": "extractor"},
                )
                time.sleep(_IDLE_SEC)
                continue

            success = _process_one(
                item, url_repo, domain_repo,
                fetcher, headless_fetcher, limiter, extractor, sink, worker_id
            )
            processed += 1
            if success:
                urls_success += 1
            else:
                urls_failed += 1


def _process_one(
    item: dict,
    url_repo: ArticleUrlRepo,
    domain_repo: DomainRepo,
    fetcher: HttpFetcher,
    headless_fetcher: "HeadlessFetcher",
    limiter: RateLimiter,
    extractor: DefaultExtractor,
    sink: Sink,
    worker_id: str,
) -> bool:
    """URL 하나를 처리한다. 성공 시 True, 실패 시 False 반환."""
    item_id = item["id"]
    url     = item["url"]
    host    = item["host"]
    portal  = item["portal_type"]
    keyword = item.get("keyword", "")
    attempt = item["attempt_count"]

    extra = {
        "phase": "extract", "worker_id": worker_id,
        "host": host, "url_id": str(item_id), "component": "extractor",
    }

    # 해당 도메인이 차단 상태(cooldown)인지 확인한다.
    # 429(Too Many Requests) 등을 받으면 domain_repo.set_cooldown() 으로 쿨다운이 설정된다.
    domain = domain_repo.get(host)
    if domain and domain.get("cooldown_until"):
        cooldown_until = domain["cooldown_until"]
        # PyMySQL 이 반환하는 DATETIME 은 타임존 없는 UTC 값이다.
        now_utc = datetime.utcnow()
        if isinstance(cooldown_until, datetime) and cooldown_until > now_utc:
            url_repo.mark_failed(
                item_id,
                error_code=ErrorCode.FETCH_BLOCKED,
                error_msg=f"domain on cooldown until {cooldown_until.isoformat()}",
                is_permanent=False,
                next_retry_at=cooldown_until,
            )
            return False

    # 레이트 리밋
    limiter.wait(host)

    render_mode = (domain or {}).get("render_mode", RenderMode.STATIC)
    try:
        fr = fetch_by_render_mode(url, render_mode, fetcher, headless_fetcher)
    except Exception as exc:
        error_code, is_permanent = classify_exception(exc)
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.warning(
            f"fetch error url={url}",
            extra={**extra, "error_code": error_code.value},
        )
        _handle_failure(url_repo, domain_repo, item_id, host, attempt,
                        error_code, error_msg, is_permanent)
        return False

    if fr.status_code >= 400:
        error_code, is_permanent = classify_http(fr.status_code)
        error_msg = f"HTTP {fr.status_code}"
        logger.warning(
            f"fetch {error_msg} url={url}",
            extra={**extra, "error_code": error_code.value},
        )
        _handle_failure(url_repo, domain_repo, item_id, host, attempt,
                        error_code, error_msg, is_permanent)
        return False

    # Extract
    result = extractor.extract(
        url=fr.url, html=fr.html, host=host,
        portal_type=portal, keyword=keyword,
    )

    if isinstance(result, ExtractionFailure):
        logger.warning(
            f"extract failed url={url} msg={result.error_msg}",
            extra={**extra, "error_code": result.error_code.value},
        )
        _handle_failure(url_repo, domain_repo, item_id, host, attempt,
                        result.error_code, result.error_msg, result.is_permanent)
        return False

    # Sink
    try:
        sink.write(result)
    except Exception as exc:
        logger.exception(f"sink write failed url={url}", extra=extra)
        domain_repo.upsert_health(host, success=False, body_len=None)
        url_repo.mark_failed(
            item_id,
            error_code=ErrorCode.UNKNOWN,
            error_msg=f"sink error: {exc}",
            is_permanent=False,
            next_retry_at=next_retry_at(attempt),
        )
        return False

    url_repo.mark_stored(item_id, extraction_method=result.extraction_method)
    domain_repo.upsert_health(host, success=True, body_len=result.body_len)
    logger.info(
        f"stored url={url} method={result.extraction_method} body={result.body_len}",
        extra=extra,
    )
    return True


def _handle_failure(
    url_repo: ArticleUrlRepo,
    domain_repo: DomainRepo,
    item_id: int,
    host: str,
    attempt: int,
    error_code: ErrorCode,
    error_msg: str,
    is_permanent: bool,
) -> None:
    """실패를 기록하고 다음 상태를 결정한다.

    결정 순서:
      1. 시도 횟수가 MAX_ATTEMPTS 에 도달하면 → dead (더 이상 재시도 없음)
      2. 영구 오류(404 등) 이면              → failed_permanent (재시도 없음)
      3. 그 외 일시 오류                     → failed_transient (백오프 후 재시도)
    """
    domain_repo.upsert_health(host, success=False, body_len=None)

    if attempt + 1 >= config.MAX_ATTEMPTS:
        url_repo.mark_dead(item_id, error_code, error_msg)
    elif is_permanent:
        url_repo.mark_failed(item_id, error_code, error_msg, True, None)
    else:
        url_repo.mark_failed(item_id, error_code, error_msg, False,
                             next_retry_at=next_retry_at(attempt))


def _flush_log(
    log_repo: CollectionLogRepo,
    portal: str,
    worker_id: str,
    started_at: datetime,
    started_mono: float,
    attempted: int,
    success: int,
    failed: int,
) -> None:
    if attempted == 0:
        return
    duration_ms = int((time.monotonic() - started_mono) * 1000)
    try:
        log_repo.insert_extraction(ExtractionLog(
            portal_type    = portal,
            worker_id      = worker_id,
            started_at     = started_at,
            duration_ms    = duration_ms,
            urls_attempted = attempted,
            urls_success   = success,
            urls_failed    = failed,
        ))
    except Exception:
        logger.exception("failed to write extraction log")
