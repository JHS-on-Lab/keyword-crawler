"""
Solr 연결 확인 스크립트.

실행:
  python scripts/check_solr.py

접속 모드 (.env 설정에 따라 자동 선택):
  SOLR_URL 이 있으면  → 직접 접속
  SOLR_URL 이 없으면  → SOLR_RUNTIME_NAME 으로 t_crawl_runtime 조회 후 접속

확인 항목:
  1. solr_url 결정 (직접 or DB 조회)
  2. Solr ping (/admin/ping)
  3. 저장된 문서 수 (q=*:*, rows=0)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from app import config


def _get_solr_url() -> str:
    """SOLR_URL(직접) 또는 SOLR_RUNTIME_NAME(DB 조회) 로 solr_url 을 결정한다."""
    if config.SOLR_URL:
        print(f"[모드] 직접 접속 (SOLR_URL)")
        return config.SOLR_URL

    if not config.SOLR_RUNTIME_NAME:
        print("[오류] SOLR_URL 또는 SOLR_RUNTIME_NAME 을 .env 에 설정하세요.")
        sys.exit(1)

    print(f"[모드] DB 조회 (SOLR_RUNTIME_NAME={config.SOLR_RUNTIME_NAME})")
    from app.repository.db import db_context
    from app.repository.crawl_runtime_repo import CrawlRuntimeRepo

    with db_context() as engine:
        url = CrawlRuntimeRepo(engine).get_solr_url(config.SOLR_RUNTIME_NAME)

    if not url:
        print(f"[오류] t_crawl_runtime 에서 '{config.SOLR_RUNTIME_NAME}' 을 찾을 수 없거나 use_yn='N' 입니다.")
        sys.exit(1)

    return url


def main() -> None:
    solr_url = _get_solr_url().rstrip("/")
    print(f"Solr URL : {solr_url}")
    print()

    # 1. Ping
    print("1. Ping 테스트...")
    try:
        resp = httpx.get(f"{solr_url}/admin/ping", timeout=5)
        resp.raise_for_status()
        status = resp.json().get("status") or resp.text
        print(f"   상태: OK")
    except httpx.ConnectError:
        print(f"   [오류] {solr_url} 에 연결할 수 없습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"   [오류] {e}")
        sys.exit(1)

    # 2. 문서 수
    print("2. 문서 수 확인...")
    try:
        resp = httpx.get(
            f"{solr_url}/select",
            params={"q": "*:*", "rows": "0", "wt": "json"},
            timeout=5,
        )
        resp.raise_for_status()
        num_found = resp.json().get("response", {}).get("numFound", 0)
        print(f"   저장된 문서 수: {num_found:,}건")
    except Exception as e:
        print(f"   [오류] {e}")
        sys.exit(1)

    print()
    print("Solr 연결 성공.")


if __name__ == "__main__":
    main()
