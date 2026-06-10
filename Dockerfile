# ----------------------------------------------------------------
# 베이스 이미지: mcr.microsoft.com/playwright/python
#
# Playwright 공식 이미지. Chromium 브라우저와 실행에 필요한 시스템
# 의존성이 모두 포함돼 있다.
# 태그 형식: v{playwright버전}-{ubuntu코드명}
#   noble = Ubuntu 24.04 LTS
# ----------------------------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.59.0-noble

WORKDIR /app

# ----------------------------------------------------------------
# 시스템 라이브러리 설치
#
# Playwright 이미지에 Chromium 관련 의존성은 이미 포함돼 있다.
# lxml(XPath 파싱) 이 C 확장이라 컴파일 도구와 XML 헤더가 별도로 필요하다.
#
# gcc         : C 확장 패키지 컴파일러
# libxml2-dev : lxml XML 파싱 헤더
# libxslt1-dev: lxml XSLT 변환 헤더
# ----------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------
# Python 패키지 설치
#
# requirements.txt 만 먼저 복사하는 이유:
#   Docker는 각 명령(RUN, COPY 등)의 결과를 레이어로 캐시한다.
#   소스코드(app/)가 바뀌어도 requirements.txt 가 그대로라면
#   이 RUN pip install 레이어는 캐시를 재사용한다. → 재빌드 시간 대폭 단축.
#
# --no-cache-dir: pip 다운로드 캐시를 저장하지 않음 → 이미지 크기 절감
# ----------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------------
# 애플리케이션 코드 복사
#
# .env 는 민감 정보 없는 공통 기본값만 담고 있어 이미지에 포함한다.
# .env.dev / .env.prod 는 이미지에 넣지 않는다 (.dockerignore 로 제외).
#   → 환경별 접속 정보는 컨테이너 실행 시 --env-file 로 주입한다.
# ----------------------------------------------------------------
COPY app/ app/
RUN chmod -R o+rX /app

COPY .env .

# ----------------------------------------------------------------
# CMD / ENTRYPOINT 없음
#
# 역할(--role)과 포털(--portal)이 컨테이너마다 다르므로
# 실행 명령은 run.sh 에서 docker run 인자로 지정한다.
# ----------------------------------------------------------------
