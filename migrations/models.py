"""
SQLAlchemy Core 테이블 정의 — 설계 문서 5.1절 기준.
ORM 매핑 없이 MetaData + Table 로만 정의해 Alembic autogenerate에 사용.
"""

from sqlalchemy import (
    MetaData, Table, Column,
    BigInteger, String, Integer, SmallInteger, Boolean, Float,
    DateTime, Date, Text, JSON,
    UniqueConstraint, Index,
)
from sqlalchemy.sql import func

metadata = MetaData()

# ---------------------------------------------------------------------------
# keyword
# ---------------------------------------------------------------------------
keyword = Table(
    "t_keyword",
    metadata,
    # ── 식별 ──────────────────────────────────────────────────────────────
    Column("id",               BigInteger,  primary_key=True, autoincrement=True),
    Column("keyword",          String(255), nullable=False,
           comment="검색어 또는 식별자. NAVER_STOCK 은 종목코드 (예: 005930)"),
    Column("portal_type",      String(20),  nullable=False,
           comment="NAVER_NEWS | DAUM_NEWS | GOOGLE_NEWS | BAIDU_NEWS | NAVER_STOCK"),
    Column("display_name",     String(100), nullable=True,
           comment="사람이 읽기 쉬운 라벨. NAVER_STOCK: 종목명, GOOGLE: 다국어 키워드 설명 등"),
    # ── 상태 / 설정 ───────────────────────────────────────────────────────
    Column("enabled",          Boolean,     nullable=False, default=True,
           comment="false = 비활성화. disabled_reason 컬럼에 이유 기록"),
    Column("disabled_reason",  String(200), nullable=True,
           comment="비활성화 이유. 예: '수동 중지' | '상장폐지' | '연속 5회 403'"),
    Column("priority",         Integer,     nullable=False, default=0,
           comment="수집 우선순위. 높을수록 먼저 처리 (claim_next ORDER BY priority DESC)"),
    # ── 스케줄링 ──────────────────────────────────────────────────────────
    Column("interval_seconds", Integer,     nullable=False, default=86400,
           comment="수집 주기(초). 기본 86400 = 24시간"),
    Column("next_discover_at", DateTime,    nullable=True, index=True,
           comment="다음 수집 예정 시각(UTC). NULL 또는 과거이면 즉시 수집 대상"),
    Column("retry_pending",    SmallInteger(), nullable=False, server_default="0",
           comment="다음 수집 시 full scan 필요 여부. 수집 중단(403 등) 시 1, 성공 완료 시 0"),
    UniqueConstraint("keyword", "portal_type", name="uq_keyword_portal"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

# ---------------------------------------------------------------------------
# article_url  (큐 + 상태 기계 + 실패 보관소)
# ---------------------------------------------------------------------------
# status enum 값: discovered | extracting | stored
#                 failed_transient | failed_permanent | dead
article_url = Table(
    "t_article_url",
    metadata,
    Column("id",               BigInteger,  primary_key=True, autoincrement=True),
    Column("url",              Text,        nullable=False),
    Column("url_hash",         String(64),  nullable=False),          # sha256 hex
    Column("host",             String(255), nullable=False),
    Column("keyword_id",       BigInteger,  nullable=True),           # FK — 무결성은 앱 레이어
    Column("portal_type",      String(20),  nullable=False),
    Column("status",           String(30),  nullable=False, default="discovered", index=True),
    Column("attempt_count",    Integer,     nullable=False, default=0),
    Column("last_error_code",  String(50),  nullable=True),
    Column("last_error_msg",   String(500), nullable=True),
    Column("next_retry_at",    DateTime,    nullable=True),
    Column("claimed_at",       DateTime,    nullable=True),
    Column("claimed_by",       String(100), nullable=True),
    Column("is_manual",        Boolean,     nullable=False, default=False),
    Column("priority",         Integer,     nullable=False, default=0),
    Column("extraction_method",String(50),  nullable=True),
    Column("collected_date",   Date,        nullable=True,  index=True),  # 날짜(KST) — 파티션·필터용
    Column("created_at",       DateTime,    nullable=False, server_default=func.now()),
    Column("updated_at",       DateTime,    nullable=False, server_default=func.now(),
           onupdate=func.now()),
    UniqueConstraint("url_hash", name="uq_article_url_hash"),
    # 점유 쿼리용: WHERE status=? AND next_retry_at<=? ORDER BY priority DESC
    Index("ix_article_url_claim", "status", "next_retry_at", "priority"),
    Index("ix_article_url_host",  "host"),
    Index("ix_article_url_keyword", "keyword_id"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

# ---------------------------------------------------------------------------
# domain  (도메인별 예외 — 규칙 + 정책 + 차단기 + 건강 지표)
# 모든 도메인이 행을 갖지 않음. 오버라이드 필요한 도메인만 존재.
# ---------------------------------------------------------------------------
domain = Table(
    "t_domain",
    metadata,
    Column("host",             String(255), primary_key=True),
    Column("rules_json",       JSON,        nullable=True),
    Column("rules_enabled",    Boolean,     nullable=False, default=True),
    Column("rules_version",    Integer,     nullable=False, default=1),
    Column("crawl_delay_ms",   Integer,     nullable=True),           # NULL = 전역 기본값 사용
    Column("render_mode",      String(20),  nullable=True),           # static | headless | NULL
    Column("proxy_tier",       String(50),  nullable=True),
    Column("cooldown_until",   DateTime,    nullable=True),
    Column("recent_fail_count",Integer,     nullable=False, default=0),
    Column("success_rate",     Float,       nullable=True),
    Column("avg_body_len",     Integer,     nullable=True),
    Column("updated_at",       DateTime,    nullable=False, server_default=func.now(),
           onupdate=func.now()),
    Column("updated_by",       String(100), nullable=True),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)

# ---------------------------------------------------------------------------
# collection_log  (발견·추출 실행 이력)
#
# run_type별 사용 컬럼:
#   discovery  : keyword_id, urls_found, urls_inserted, urls_skipped, error_msg
#   extraction : urls_attempted, urls_success, urls_failed
#
# error_msg: discovery 런이 예외로 중단됐을 때 이유 기록. NULL = 정상 완료.
# ---------------------------------------------------------------------------
collection_log = Table(
    "t_collection_log",
    metadata,
    Column("id",             BigInteger,  primary_key=True, autoincrement=True),
    Column("run_type",       String(20),  nullable=False),           # discovery | extraction
    Column("run_date",       Date,        nullable=False),           # KST 기준 일자 (일별 롤업)
    Column("keyword_id",     BigInteger,  nullable=True),            # discovery만 해당
    Column("portal_type",    String(20),  nullable=False),
    Column("worker_id",      String(100), nullable=False),
    Column("started_at",     DateTime,    nullable=False),
    Column("duration_ms",    Integer,     nullable=False),
    # discovery 전용
    Column("urls_found",     Integer,     nullable=True),
    Column("urls_inserted",  Integer,     nullable=True),
    Column("urls_skipped",   Integer,     nullable=True),
    # extraction 전용
    Column("urls_attempted", Integer,     nullable=True),
    Column("urls_success",   Integer,     nullable=True),
    Column("urls_failed",    Integer,     nullable=True),
    # 공통 — 런 실패 시 이유 (NULL = 정상 완료)
    Column("error_msg",      String(500), nullable=True),
    Column("created_at",     DateTime,    nullable=False, server_default=func.now()),
    Index("ix_collection_log_date_type",    "run_date", "run_type"),
    Index("ix_collection_log_keyword_date", "keyword_id", "run_date"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_unicode_ci",
)
