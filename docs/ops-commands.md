# 운영 명령어 가이드

## 구조 이해

```
Discovery (발견)          Extraction (추출)
────────────────         ────────────────────
포털 검색 페이지 스크랩   article_url 큐에서 꺼내
  → article_url 에         → 본문 페이지 HTTP 요청
    URL 적재                → 제목·본문 파싱
                            → JSONL 저장
```

둘은 완전히 독립 프로세스다. Discovery 가 URL 을 쌓으면 Extraction 이 비우는 구조.
같은 이미지를 `--role` 인자만 바꿔 띄운다.

---

## 1. 워커 실행

### Discovery (발견)

```bash
# 포털별 독립 실행 (권장 — 포털마다 차단 양상이 다름)
python -m app --role discovery --portal naver_news
python -m app --role discovery --portal naver_stock
python -m app --role discovery --portal daum_news
python -m app --role discovery --portal google_news
python -m app --role discovery --portal baidu_news

# 단일 프로세스로 전체 포털 처리 (소규모 운영)
python -m app --role discovery --portal all

# 워커 ID 명시 (같은 포털 여러 개 띄울 때)
python -m app --role discovery --portal naver_news --worker-id disc-naver-1
python -m app --role discovery --portal naver_news --worker-id disc-naver-2
```

### Extraction (추출)

```bash
# 전체 포털 URL 처리 (기본)
python -m app --role extraction

# 특정 포털 URL 만 처리
python -m app --role extraction --portal naver_news

# 복수 추출 워커 (worker-id 구분 필수)
python -m app --role extraction --worker-id ext-1
python -m app --role extraction --worker-id ext-2
python -m app --role extraction --worker-id ext-3
```

---

## 2. 수동 추출 스크립트

```bash
# 특정 URL 추출 테스트 — 파일 미저장, 결과만 출력
python scripts/run_extraction.py --url "https://finance.naver.com/item/board_read.naver?code=000660&nid=421731371" --dry-run

# 특정 URL 추출 + portal/keyword 컨텍스트 지정
python scripts/run_extraction.py --url "https://..." --portal NAVER_STOCK --keyword 000660

# 특정 URL 추출 + 파일 저장
python scripts/run_extraction.py --url "https://..." --portal NAVER_NEWS --keyword 삼성전자

# DB 에서 discovered URL 하나 꺼내 추출
python scripts/run_extraction.py

# 특정 포털 URL 만 꺼내 추출
python scripts/run_extraction.py --portal NAVER_NEWS

# DB 모드 dry-run (URL 을 꺼내되 파일/DB 상태 변경 없음)
python scripts/run_extraction.py --portal NAVER_STOCK --dry-run
```

---

## 3. 수동 발견 스크립트

```bash
# 특정 키워드 테스트 — DB 미기록, 네트워크만
python scripts/run_discovery.py --portal naver_news --keyword 삼성전자 --dry-run

# 특정 키워드 실행 + DB 저장 (keyword 테이블에 등록된 키워드만 허용)
python scripts/run_discovery.py --portal naver_news --keyword 삼성전자

# DB 에서 due 키워드 자동 선택 + 실행
python scripts/run_discovery.py --portal naver_news

# DB 에서 due 키워드 선택 — URL 출력만, DB 변경 없음
python scripts/run_discovery.py --portal naver_news --dry-run

# 페이지 수 제한 (기본값 초과 시)
python scripts/run_discovery.py --portal naver_news --keyword 삼성전자 --max-pages 2
```

---

## 4. DB 초기화 / 마이그레이션

```bash
# 마이그레이션 최신 상태로 적용
alembic upgrade head

# 현재 적용된 버전 확인
alembic current

# 마이그레이션 이력 조회
alembic history --verbose

# 한 단계 롤백
alembic downgrade -1

# 특정 버전으로 롤백
alembic downgrade <revision_id>
```

---

## 5. 테이블 관리

```bash
# 스키마 검증 (테이블·컬럼·인덱스 누락 확인)
python scripts/verify_schema.py

# DB 연결 확인
python scripts/check_db.py

# 특정 테이블 데이터 삭제 (확인 프롬프트 있음)
python scripts/truncate_table.py --table article_url
python scripts/truncate_table.py --table collection_log
python scripts/truncate_table.py --table keyword

# 전체 테이블 초기화 (주의)
python scripts/truncate_table.py --all
```

---

## 6. 환경변수 (`.env`)

```dotenv
# DB 접속
RDS_HOST=
RDS_PORT=3306
RDS_USER=
RDS_PASSWORD=
RDS_DB=

# SSH 터널 (로컬에서 RDS 직접 접근 시)
TUNNEL_ENABLED=true
TUNNEL_SSH_HOST=
TUNNEL_SSH_USER=ubuntu
TUNNEL_SSH_KEY_PATH=
TUNNEL_LOCAL_PORT=13306

# 워커 동작
WORKER_ID=worker-1
EXTRACTION_CONCURRENCY=4
MAX_ATTEMPTS=5

# 파일 저장
SINK_TYPE=file           # file | solr
FILE_SINK_DIR=./data
LOG_DIR=./logs

# Solr (SINK_TYPE=solr 시)
SOLR_URL=http://localhost:8983/solr/news
SOLR_BATCH_SIZE=100          # 버퍼 flush 단위
SOLR_COMMIT_WITHIN_MS=5000   # flush 후 Solr 커밋 완료 제한(ms). commit=true 대신 사용해 병목 방지

# 포털별 최대 페이지 수
NAVER_MAX_PAGES=10
DAUM_MAX_PAGES=10
DAUM_NEWS_ALL=true           # true=전체 언론사(기본), false=뉴스제휴 언론사만
GOOGLE_MAX_PAGES=5
NAVER_STOCK_MAX_PAGES=5

# 백오프 / 타임아웃
BACKOFF_BASE_SECONDS=30
BACKOFF_MAX_SECONDS=3600
CLAIM_TIMEOUT_SECONDS=300

# 로깅
LOG_LEVEL=INFO
LOG_ROTATION=daily        # daily | size
HEARTBEAT_INTERVAL_SECONDS=60
```

---

## 7. Docker Compose 예시

```yaml
services:
  # 포털별 발견 워커
  discover-naver-news:
    image: keyword-collector:latest
    command: ["--role", "discovery", "--portal", "naver_news"]
    env_file: .env

  discover-naver-stock:
    image: keyword-collector:latest
    command: ["--role", "discovery", "--portal", "naver_stock"]
    env_file: .env

  discover-daum:
    image: keyword-collector:latest
    command: ["--role", "discovery", "--portal", "daum_news"]
    env_file: .env

  discover-google:
    image: keyword-collector:latest
    command: ["--role", "discovery", "--portal", "google_news"]
    env_file: .env

  # 추출 워커 (병렬 확장)
  extraction:
    image: keyword-collector:latest
    command: ["--role", "extraction"]
    env_file: .env
    deploy:
      replicas: 3
```

---

## 8. article_url 상태값 참조

| status | 의미 | 다음 행동 |
|---|---|---|
| `discovered` | 수집 대기 | 추출 워커가 자동 처리 |
| `extracting` | 추출 중 | — (reaper 가 타임아웃 감시) |
| `stored` | 완료 | — |
| `failed_transient` | 일시 실패 | `next_retry_at` 이후 자동 재시도 |
| `failed_permanent` | 영구 실패 (404 등) | 수동 재투입 필요 |
| `dead` | 최대 시도 초과 | 수동 재투입 필요 |

```sql
-- 상태별 현황
SELECT portal_type, status, COUNT(*) AS cnt
FROM t_article_url
GROUP BY portal_type, status
ORDER BY portal_type, status;

-- failed/dead URL 재투입 (특정 포털)
UPDATE t_article_url
SET status = 'discovered', next_retry_at = NOW(), attempt_count = 0
WHERE status IN ('failed_permanent', 'dead')
  AND portal_type = 'NAVER_NEWS';

-- due 키워드 현황
SELECT portal_type, COUNT(*) AS total,
       SUM(enabled = 1) AS enabled,
       SUM(next_discover_at IS NULL OR next_discover_at <= NOW()) AS due_now
FROM t_keyword
GROUP BY portal_type;
```
