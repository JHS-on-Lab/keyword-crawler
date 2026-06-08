"""
스키마 검증: 테이블·컬럼·인덱스·제약 확인.
실행: python scripts/verify_schema.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, inspect
from app.repository.db import db_context

EXPECTED_TABLES = {"t_keyword", "t_article_url", "t_domain", "t_collection_log", "alembic_version"}

EXPECTED_COLUMNS = {
    "t_keyword": {
        "id", "keyword", "portal_type", "interval_seconds",
        "next_discover_at", "retry_pending",
        "enabled", "priority", "display_name", "disabled_reason",
    },
    "t_article_url": {
        "id", "url", "url_hash", "host", "keyword_id", "portal_type",
        "status", "attempt_count", "last_error_code", "last_error_msg",
        "next_retry_at", "claimed_at", "claimed_by", "is_manual", "priority",
        "extraction_method", "collected_date", "created_at", "updated_at",
    },
    "t_domain": {
        "host", "rules_json", "rules_enabled", "rules_version",
        "crawl_delay_ms", "render_mode", "proxy_tier",
        "cooldown_until", "recent_fail_count", "success_rate", "avg_body_len",
        "updated_at", "updated_by",
    },
    "t_collection_log": {
        "id", "run_type", "run_date", "keyword_id", "portal_type", "worker_id",
        "started_at", "duration_ms",
        "urls_found", "urls_inserted", "urls_skipped",
        "urls_attempted", "urls_success", "urls_failed",
        "error_msg", "created_at",
    },
}

EXPECTED_INDEXES = {
    "t_article_url":    {"uq_article_url_hash", "ix_article_url_claim",
                         "ix_article_url_host", "ix_article_url_keyword",
                         "ix_article_url_status", "ix_article_url_collected_date"},
    "t_keyword":        {"uq_keyword_portal", "ix_keyword_next_discover_at"},
    "t_collection_log": {"ix_collection_log_date_type", "ix_collection_log_keyword_date"},
}


def main():
    ok = True

    with db_context() as engine:
        insp   = inspect(engine)
        tables = set(insp.get_table_names())

        print("=== 테이블 ===")
        missing_tables = EXPECTED_TABLES - tables
        for t in sorted(EXPECTED_TABLES):
            status = "OK" if t in tables else "MISSING"
            print(f"  [{status:7s}] {t}")
        if missing_tables:
            ok = False

        print()
        for table, expected_cols in EXPECTED_COLUMNS.items():
            print(f"=== {table} ===")
            if table not in tables:
                print(f"  [SKIP] 테이블 없음 — 컬럼·인덱스 검사 생략")
                ok = False
                continue

            actual_cols = {c["name"] for c in insp.get_columns(table)}
            actual_idxs = {i["name"] for i in insp.get_indexes(table)}
            missing_cols = expected_cols - actual_cols
            extra_cols   = actual_cols - expected_cols

            if missing_cols:
                print(f"  [MISSING cols] {sorted(missing_cols)}")
                ok = False
            else:
                print(f"  [OK] 컬럼 {len(actual_cols)}개")

            if extra_cols:
                print(f"  [extra  cols] {sorted(extra_cols)}")

            exp_idx = EXPECTED_INDEXES.get(table, set())
            missing_idx = exp_idx - actual_idxs
            if missing_idx:
                print(f"  [MISSING idx ] {sorted(missing_idx)}")
                ok = False
            else:
                print(f"  [OK] 인덱스 {len(actual_idxs)}개")

        print()
        if "t_keyword" in tables:
            with engine.begin() as conn:
                conn.execute(text("SELECT id FROM t_keyword LIMIT 1 FOR UPDATE"))
                print("FOR UPDATE 지원: OK")

    print()
    print("스키마 검증 완료." if ok else "스키마 검증 실패 — 위 MISSING 항목을 확인하세요.")


if __name__ == "__main__":
    main()
