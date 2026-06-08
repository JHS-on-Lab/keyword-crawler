-- ============================================================
-- keyword-collector schema  (DBA 전달용 — 최종 버전)
-- MySQL 8.0+  /  InnoDB  /  utf8mb4_unicode_ci
-- ============================================================

CREATE TABLE t_keyword (
  id               BIGINT        NOT NULL AUTO_INCREMENT,
  keyword          VARCHAR(255)  NOT NULL COMMENT '검색어 또는 식별자. NAVER_STOCK 은 종목코드 (예: 005930)',
  portal_type      VARCHAR(20)   NOT NULL COMMENT 'NAVER_NEWS | DAUM_NEWS | GOOGLE_NEWS | BAIDU_NEWS | NAVER_STOCK',
  display_name     VARCHAR(100)           COMMENT '사람이 읽기 쉬운 라벨. NAVER_STOCK: 종목명, GOOGLE: 다국어 키워드 설명 등',
  enabled          TINYINT(1)    NOT NULL DEFAULT 1   COMMENT 'false = 비활성화. disabled_reason 컬럼에 이유 기록',
  disabled_reason  VARCHAR(200)           COMMENT '비활성화 이유. 예: 수동 중지 | 상장폐지 | 연속 5회 403',
  priority         INT           NOT NULL DEFAULT 0   COMMENT '수집 우선순위. 높을수록 먼저 처리 (ORDER BY priority DESC)',
  interval_seconds INT           NOT NULL DEFAULT 86400 COMMENT '수집 주기(초). 기본 86400 = 24시간',
  next_discover_at DATETIME               COMMENT '다음 수집 예정 시각(UTC). NULL 또는 과거이면 즉시 수집 대상',
  retry_pending    TINYINT(1)    NOT NULL DEFAULT 0 COMMENT '다음 수집 시 full scan 필요 여부. 수집 중단(403 등) 시 1, 성공 완료 시 0',
  PRIMARY KEY (id),
  UNIQUE KEY uq_keyword_portal        (keyword, portal_type),
  KEY        ix_keyword_next_discover_at (next_discover_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE t_article_url (
  id                BIGINT        NOT NULL AUTO_INCREMENT,
  url               TEXT          NOT NULL,
  url_hash          VARCHAR(64)   NOT NULL,
  host              VARCHAR(255)  NOT NULL,
  keyword_id        BIGINT,
  portal_type       VARCHAR(20)   NOT NULL,
  status            VARCHAR(30)   NOT NULL DEFAULT 'discovered',
  attempt_count     INT           NOT NULL DEFAULT 0,
  last_error_code   VARCHAR(50),
  last_error_msg    VARCHAR(500),
  next_retry_at     DATETIME,
  claimed_at        DATETIME,
  claimed_by        VARCHAR(100),
  is_manual         TINYINT(1)    NOT NULL DEFAULT 0,
  priority          INT           NOT NULL DEFAULT 0,
  extraction_method VARCHAR(50),
  collected_date    DATE,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_article_url_hash      (url_hash),
  KEY        ix_article_url_status    (status),
  KEY        ix_article_url_collected_date (collected_date),
  KEY        ix_article_url_claim     (status, next_retry_at, priority),
  KEY        ix_article_url_host      (host),
  KEY        ix_article_url_keyword   (keyword_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE t_domain (
  host              VARCHAR(255)  NOT NULL,
  rules_json        JSON,
  rules_enabled     TINYINT(1)    NOT NULL DEFAULT 1,
  rules_version     INT           NOT NULL DEFAULT 1,
  crawl_delay_ms    INT,
  render_mode       VARCHAR(20),
  proxy_tier        VARCHAR(50),
  cooldown_until    DATETIME,
  recent_fail_count INT           NOT NULL DEFAULT 0,
  success_rate      FLOAT,
  avg_body_len      INT,
  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  updated_by        VARCHAR(100),
  PRIMARY KEY (host)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE t_collection_log (
  id             BIGINT        NOT NULL AUTO_INCREMENT,
  run_type       VARCHAR(20)   NOT NULL COMMENT 'discovery | extraction',
  run_date       DATE          NOT NULL COMMENT 'KST 기준 일자 (일별 롤업)',
  keyword_id     BIGINT                 COMMENT 'discovery 런만 해당',
  portal_type    VARCHAR(20)   NOT NULL,
  worker_id      VARCHAR(100)  NOT NULL,
  started_at     DATETIME      NOT NULL,
  duration_ms    INT           NOT NULL,
  urls_found     INT,
  urls_inserted  INT,
  urls_skipped   INT,
  urls_attempted INT,
  urls_success   INT,
  urls_failed    INT,
  error_msg      VARCHAR(500)           COMMENT 'NULL = 정상 완료',
  created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_collection_log_date_type    (run_date, run_type),
  KEY ix_collection_log_keyword_date (keyword_id, run_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
