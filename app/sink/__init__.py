"""
Sink 팩토리.

.env 의 SINK_TYPE 값에 따라 FileSink 또는 SolrSink 를 반환한다.

  SINK_TYPE=file  (기본) → FileSink  — data/{날짜}/{소스}-{worker_id}.jsonl 에 저장
  SINK_TYPE=solr         → SolrSink  — t_crawl_runtime 에서 조회한 solr_url 로 upsert
"""

from __future__ import annotations

from sqlalchemy import Engine

from app import config
from app.ports import Sink


def make_sink(engine: Engine) -> Sink:
    """SINK_TYPE 환경변수에 따라 적절한 Sink 를 반환한다."""
    sink_type = config.SINK_TYPE.lower()

    if sink_type == "solr":
        from app.sink.solr_sink import SolrSink
        return SolrSink(_resolve_solr_url(engine))

    # 기본값: file
    from app.sink.file_sink import FileSink
    return FileSink()


def _resolve_solr_url(engine: Engine) -> str:
    """t_crawl_runtime 테이블에서 SOLR_RUNTIME_NAME 에 해당하는 solr_url 을 가져온다."""
    from app.repository.crawl_runtime_repo import CrawlRuntimeRepo
    runtime_name = config.SOLR_RUNTIME_NAME
    url = CrawlRuntimeRepo(engine).get_solr_url(runtime_name)
    if not url:
        raise RuntimeError(
            f"t_crawl_runtime 에서 runtime_name='{runtime_name}' 을 찾을 수 없거나 "
            f"use_yn='N' 입니다."
        )
    return url
