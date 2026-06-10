#!/usr/bin/env bash
# ----------------------------------------------------------------
# run.sh — 워커 컨테이너 하나를 실행한다.
#
# 같은 이미지로 역할(role)과 포털(portal)을 바꿔가며 여러 번 호출해
# 원하는 수만큼 워커를 띄울 수 있다.
#
# 사용법:
#   ./deploy/run.sh <role> <portal> <worker_id>
#
# 인자:
#   role       discovery  — 키워드로 기사 URL 을 수집하는 워커
#              extraction — 수집된 URL 에서 본문을 추출하는 워커
#
#   portal     naver_news | daum_news | google_news | naver_stock | all
#              discovery 워커가 어떤 포털을 담당할지 지정.
#              extraction 워커는 보통 all 을 사용한다.
#
#   worker_id  컨테이너를 구별하는 고유 이름. 로그 파일명과 JSONL 파일명에 포함된다.
#              같은 역할/포털로 여러 컨테이너를 띄울 때 각각 다른 이름을 사용한다.
#
# 예시:
#   ./deploy/run.sh discovery naver_news  disc-naver-1
#   ./deploy/run.sh discovery daum_news   disc-daum-1
#   ./deploy/run.sh extraction all        extr-1
# ----------------------------------------------------------------

set -e  # 오류 발생 시 즉시 중단

# ----------------------------------------------------------------
# 인자 수신
# ----------------------------------------------------------------

ROLE="${1}"       # 첫 번째 인자: discovery | extraction
PORTAL="${2}"     # 두 번째 인자: naver_news | daum_news | ... | all
WORKER_ID="${3}"  # 세 번째 인자: 컨테이너 고유 식별자

# ----------------------------------------------------------------
# 인자 유효성 검사
#
# -z: 문자열이 비어있으면 참(true)
# ----------------------------------------------------------------

if [[ -z "${ROLE}" || -z "${PORTAL}" || -z "${WORKER_ID}" ]]; then
    echo "오류: 인자가 부족합니다."
    echo ""
    echo "사용법: $0 <role> <portal> <worker_id>"
    echo ""
    echo "  role    : discovery | extraction"
    echo "  portal  : naver_news | daum_news | google_news | naver_stock | all"
    echo "  worker_id: 고유 식별자 (예: disc-naver-1, extr-1)"
    echo ""
    echo "예시:"
    echo "  $0 discovery naver_news disc-naver-1"
    echo "  $0 extraction all       extr-1"
    exit 1
fi

# ----------------------------------------------------------------
# 경로 설정
# ----------------------------------------------------------------

# 이 스크립트(deploy/run.sh)의 위치에서 한 단계 올라가면 프로젝트 루트.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# APP_ENV: 어떤 환경 설정 파일을 사용할지 결정한다.
#   서버에 'export APP_ENV=dev' 를 .bashrc 에 설정해두면 자동으로 읽힌다.
#   설정하지 않은 경우 기본값은 "dev".
APP_ENV="${APP_ENV:-dev}"
ENV_FILE="${PROJECT_ROOT}/.env.${APP_ENV}"

# 볼륨 마운트 경로: 컨테이너 밖 호스트 서버에 로그와 출력물을 저장한다.
#   컨테이너가 재시작되거나 삭제돼도 데이터가 보존된다.
#   ~/ = 현재 사용자의 홈 디렉토리
LOG_DIR="${HOME}/apps/data/keyword-collector/logs"
OUTPUT_DIR="${HOME}/apps/data/keyword-collector/output"

# ----------------------------------------------------------------
# 환경 설정 파일 확인
# ----------------------------------------------------------------

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "오류: 환경 설정 파일을 찾을 수 없습니다: ${ENV_FILE}"
    echo "  APP_ENV=${APP_ENV} 로 실행 중입니다."
    echo "  서버에 .env.${APP_ENV} 파일이 있는지 확인하세요."
    exit 1
fi

# ----------------------------------------------------------------
# 볼륨 디렉토리 생성
#
# mkdir -p: 이미 있어도 오류 없이 넘어감. 중간 디렉토리도 함께 생성.
# ----------------------------------------------------------------

mkdir -p "${LOG_DIR}"
mkdir -p "${OUTPUT_DIR}"

# ----------------------------------------------------------------
# 기존 컨테이너 정리
#
# 같은 이름의 컨테이너가 이미 실행 중이거나 종료된 채 남아있으면
# 새 컨테이너를 시작할 수 없다. 먼저 제거한다.
#
# docker ps -a: 실행 중인 것뿐 아니라 종료된 컨테이너도 포함해 목록 출력
# --format '{{.Names}}': 이름 컬럼만 출력
# grep -q: 조용히 검색 (출력 없음). 찾으면 종료 코드 0, 못 찾으면 1.
# ----------------------------------------------------------------

CONTAINER_NAME="${WORKER_ID}"

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "▶ 기존 컨테이너 제거: ${CONTAINER_NAME}"
    # docker rm -f: 실행 중인 컨테이너도 강제 종료 후 삭제
    docker rm -f "${CONTAINER_NAME}"
fi

# ----------------------------------------------------------------
# 컨테이너 실행
# ----------------------------------------------------------------

IMAGE="keyword-collector:latest"

echo "▶ 컨테이너 시작: ${CONTAINER_NAME}"
echo "  이미지   : ${IMAGE}"
echo "  역할     : ${ROLE} / ${PORTAL}"
echo "  환경설정 : ${ENV_FILE}"
echo "  로그     : ${LOG_DIR}"
echo "  출력     : ${OUTPUT_DIR}"
echo ""

docker run \
    --detach \
    --name "${CONTAINER_NAME}" \
    --user "$(id -u):$(id -g)" \
    \
    `# 컨테이너가 비정상 종료되면 자동으로 재시작한다.` \
    `# unless-stopped: 사용자가 직접 docker stop 한 경우에는 재시작하지 않는다.` \
    --restart unless-stopped \
    \
    `# 환경 설정 파일(.env.dev 또는 .env.prod)에서 DB 접속 정보 등을 읽는다.` \
    --env-file "${ENV_FILE}" \
    \
    `# 환경 이름과 워커 ID 는 파일이 아닌 값으로 직접 주입한다.` \
    `# --env-file 보다 나중에 선언된 -e 가 우선 적용된다.` \
    -e APP_ENV="${APP_ENV}" \
    -e WORKER_ID="${WORKER_ID}" \
    \
    `# 볼륨 마운트: 호스트경로:컨테이너경로` \
    `# 컨테이너 안의 /app/logs 에 쓰는 파일이 호스트의 LOG_DIR 에 저장된다.` \
    -v "${LOG_DIR}:/app/logs" \
    -v "${OUTPUT_DIR}:/app/output" \
    \
    "${IMAGE}" \
    python -m app --role "${ROLE}" --portal "${PORTAL}"

# ----------------------------------------------------------------
# 실행 확인 안내
# ----------------------------------------------------------------

echo "✓ 시작 완료: ${CONTAINER_NAME}"
echo ""
echo "확인 명령어:"
echo "  실시간 로그  → docker logs -f ${CONTAINER_NAME}"
echo "  상태 확인    → docker ps | grep ${CONTAINER_NAME}"
echo "  컨테이너 중지 → docker stop ${CONTAINER_NAME}"
