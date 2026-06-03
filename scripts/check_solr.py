"""
Solr 연결·코어 상태 확인 스크립트.

실행:
  python scripts/check_solr.py

확인 항목:
  1. SOLR_URL 환경변수 설정 여부
  2. Solr ping (/admin/ping)
  3. 코어 기본 정보 (문서 수, 인덱스 크기)
  4. 간단한 검색 테스트 (q=*:*, rows=0)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from app import config


def main() -> None:
    solr_url = config.SOLR_URL.rstrip("/")

    if not solr_url:
        print("[오류] SOLR_URL 이 설정되지 않았습니다.")
        print("  .env 에 다음을 추가하세요:")
        print("    SOLR_URL=http://localhost:8983/solr/news")
        sys.exit(1)

    print(f"Solr URL: {solr_url}")
    print()

    # 1. Ping
    print("1. Ping 테스트...")
    try:
        resp = httpx.get(f"{solr_url}/admin/ping", timeout=5)
        resp.raise_for_status()
        status = resp.json().get("status", "unknown")
        print(f"   상태: {status}")
        if status != "OK":
            print("   [경고] Solr 응답이 OK 가 아닙니다.")
    except httpx.ConnectError:
        print(f"   [오류] {solr_url} 에 연결할 수 없습니다. Solr 가 실행 중인지 확인하세요.")
        sys.exit(1)
    except Exception as e:
        print(f"   [오류] {e}")
        sys.exit(1)

    # 2. 코어 정보
    print("2. 코어 정보...")
    try:
        resp = httpx.get(
            f"{solr_url}/select",
            params={"q": "*:*", "rows": "0", "wt": "json"},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        num_found = data.get("response", {}).get("numFound", 0)
        print(f"   저장된 문서 수: {num_found:,}건")
    except Exception as e:
        print(f"   [오류] 검색 테스트 실패: {e}")
        sys.exit(1)

    # 3. 스키마 필드 확인
    print("3. 스키마 필드 확인...")
    try:
        resp = httpx.get(f"{solr_url}/schema/fields", timeout=5)
        resp.raise_for_status()
        fields = [f["name"] for f in resp.json().get("fields", [])]
        required = {"id", "title", "body", "portal_type", "keyword", "collected_at"}
        missing  = required - set(fields)

        if missing:
            print(f"   [경고] 다음 필드가 스키마에 없습니다: {missing}")
            print("   Solr schema.xml 또는 managed-schema 에 해당 필드를 추가하세요.")
        else:
            print(f"   필수 필드 모두 확인: {sorted(required)}")
    except Exception as e:
        print(f"   [참고] 스키마 조회 실패 (권한 문제일 수 있음): {e}")

    print()
    print("Solr 연결 성공.")


if __name__ == "__main__":
    main()
