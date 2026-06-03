"""
domain 테이블 규칙 시드 스크립트.

테이블을 날렸거나 규칙을 초기화해야 할 때 실행한다.
이미 존재하는 host 는 rules_json / render_mode / crawl_delay_ms 를 덮어쓴다.

실행: python scripts/seed_domain_rules.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app import config
from app.repository.db import db_context

# ---------------------------------------------------------------------------
# 도메인 규칙 정의
# 각 항목:
#   host          : 도메인 (PK)
#   rules_json    : 추출 규칙 (None 이면 규칙 없이 render_mode 설정만)
#   rules_enabled : 규칙 활성화 여부
#   render_mode   : static | headless | headless_with_iframe
#   crawl_delay_ms: 요청 간 최소 대기 (ms). None 이면 전역 기본값 사용
#   updated_by    : 등록자 메모
# ---------------------------------------------------------------------------

_RULES: list[dict] = [
    {
        "host": "finance.naver.com",
        "render_mode": "static",
        "crawl_delay_ms": 500,
        "rules_enabled": True,
        "updated_by": "seed",
        # JSON API 직접 호출 — React SPA iframe 이라 CSS 추출 불가
        # API: m.stock.naver.com/front-api/discussion/detail?id={nid}
        "rules_json": {
            "json_api": {
                "url_template": "https://m.stock.naver.com/front-api/discussion/detail?id={nid}",
                "url_param":    "nid",
                "title":        "result.title",
                "body_html":    "result.contentHtml",
                "body_css":     ".se-module-text",
                "published_at": "result.writtenAt",
                "author":       "result.writer.nickname",
                "press":        "result.itemName",
            },
            "min_body_len": 5,
        },
    },
]

# ---------------------------------------------------------------------------

_UPSERT_SQL = text("""
    INSERT INTO domain
        (host, rules_json, rules_enabled, rules_version,
         render_mode, crawl_delay_ms, updated_by)
    VALUES
        (:host, :rules_json, :rules_enabled, 1,
         :render_mode, :crawl_delay_ms, :updated_by)
    ON DUPLICATE KEY UPDATE
        rules_json     = VALUES(rules_json),
        rules_enabled  = VALUES(rules_enabled),
        rules_version  = rules_version + 1,
        render_mode    = VALUES(render_mode),
        crawl_delay_ms = VALUES(crawl_delay_ms),
        updated_by     = VALUES(updated_by)
""")


def main() -> None:
    config.validate()

    print(f"삽입 대상: {len(_RULES)}개 도메인")

    with db_context() as engine:
        with engine.begin() as conn:
            for rule in _RULES:
                rules_json = rule.get("rules_json")
                conn.execute(_UPSERT_SQL, {
                    "host":          rule["host"],
                    "rules_json":    json.dumps(rules_json, ensure_ascii=False) if rules_json else None,
                    "rules_enabled": rule.get("rules_enabled", True),
                    "render_mode":   rule.get("render_mode"),
                    "crawl_delay_ms":rule.get("crawl_delay_ms"),
                    "updated_by":    rule.get("updated_by", "seed"),
                })
                print(f"  upserted: {rule['host']}")

    print("완료.")


if __name__ == "__main__":
    main()
