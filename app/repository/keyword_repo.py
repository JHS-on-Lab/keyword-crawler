"""
keyword 테이블 접근.

keyword 는 수집 스케줄을 담당한다.
next_discover_at 이 현재 시각보다 과거이면 "수집할 때가 됐다"는 뜻이다.

claim_next() 의 동작 원리:
  1. next_discover_at <= NOW() 인 키워드를 FOR UPDATE SKIP LOCKED 로 잠근다.
     → 다른 워커가 동시에 같은 키워드를 가져가는 것을 막는다.
  2. 잠그는 즉시, 같은 트랜잭션 안에서 next_discover_at 을 24시간 뒤로 밀어둔다.
     → 트랜잭션이 끝난 뒤에도 다른 워커가 다시 집어가지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Engine, text


class KeywordRepo:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def claim_next(self, portal: str, worker_id: str) -> dict | None:
        """
        due 상태(enabled + next_discover_at <= NOW())인 키워드를 원자적으로 점유한다.

        낙관적 클레임 패턴 (MariaDB 10.5 호환):
          1. 후보 N개를 조회 (잠금 없음)
          2. 각 후보에 대해 UPDATE WHERE 조건으로 선점 시도
          3. rowcount=1 → 내가 가져간 것 / rowcount=0 → 다른 워커가 먼저 가져간 것 → 다음 후보 시도

        반환: {id, keyword, portal_type, interval_seconds} 또는 None(없으면)
        """
        portal_filter = "" if portal.upper() == "ALL" else "AND portal_type = :portal"

        with self._engine.begin() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT id, keyword, portal_type, interval_seconds, retry_pending
                    FROM t_keyword
                    WHERE enabled = true
                      AND (next_discover_at IS NULL OR next_discover_at <= NOW())
                      {portal_filter}
                    ORDER BY priority DESC, next_discover_at ASC
                    LIMIT 20
                """),
                {"portal": portal.upper()},
            ).fetchall()

            for row in rows:
                kw = dict(row._mapping)
                result = conn.execute(
                    text("""
                        UPDATE t_keyword
                        SET next_discover_at = NOW() + INTERVAL :sec SECOND
                        WHERE id = :kid
                          AND enabled = true
                          AND (next_discover_at IS NULL OR next_discover_at <= NOW())
                    """),
                    {"sec": kw["interval_seconds"], "kid": kw["id"]},
                )
                if result.rowcount == 1:
                    return kw

        return None

    def reschedule(self, keyword_id: int, next_at: datetime) -> None:
        """next_discover_at 을 지정 시각으로 갱신한다. 403 재시도 등에 사용."""
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE t_keyword SET next_discover_at = :next_at WHERE id = :kid"),
                {"next_at": next_at, "kid": keyword_id},
            )

    def set_retry_pending(self, keyword_id: int, pending: bool) -> None:
        """retry_pending 을 갱신한다.
        - 수집 중단(403 등) 시: True → 다음 수집은 full scan 모드
        - 성공 완료 시: False → 다음 수집은 early-stop 포함 정상 모드
        """
        with self._engine.begin() as conn:
            conn.execute(
                text("UPDATE t_keyword SET retry_pending = :pending WHERE id = :kid"),
                {"pending": int(pending), "kid": keyword_id},
            )

    def list_all(self, portal: str = "ALL") -> list[dict]:
        """전체 키워드 목록 조회 (운영 확인용)."""
        portal_filter = "" if portal.upper() == "ALL" else "WHERE k.portal_type = :portal"
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT k.id, k.keyword, k.display_name, k.portal_type,
                           k.enabled, k.disabled_reason,
                           k.next_discover_at, k.priority,
                           MAX(CASE WHEN cl.error_msg IS NULL THEN cl.started_at END) AS last_discovered_at
                    FROM t_keyword k
                    LEFT JOIN t_collection_log cl
                           ON cl.keyword_id = k.id AND cl.run_type = 'discovery'
                    {portal_filter}
                    GROUP BY k.id
                    ORDER BY k.portal_type, k.keyword
                """),
                {"portal": portal.upper()},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
