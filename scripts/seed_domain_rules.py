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

    # ==========================================================================
    # JSON API 직접 호출
    # ==========================================================================

    {
        "host": "finance.naver.com",
        "render_mode": "static",
        "crawl_delay_ms": 500,
        "rules_enabled": True,
        "updated_by": "seed",
        # React SPA iframe — CSS 추출 불가, JSON API 직접 호출
        "rules_json": {
            "json_api": {
                "url_template": "https://m.stock.naver.com/front-api/discussion/detail?id={nid}",
                "url_param":    "nid",
                "title":        "result.title",
                "body_html":    "result.contentHtml",
                "body_css":     ".se-module-text",
                "published_at": "result.writtenAt",
                "author":       "result.writer.nickname",
            },
            "min_body_len": 5,
        },
    },

    # ==========================================================================
    # Daum 뷰어 (제휴 언론사 기사)
    # ==========================================================================

    {
        "host": "v.daum.net",
        "render_mode": "static",
        "crawl_delay_ms": 500,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        # div.article_view: 본문만 포함. viewrelate_wrap(관련기사)·저작권 문구 자동 제외.
        "rules_json": {
            "title":    {"css": "h3.tit_view"},
            "body":     {"css": "div.article_view"},
            "min_body_len": 100,
        },
    },

    # ==========================================================================
    # SPA / JavaScript 렌더링 필요 → render_mode: headless
    # trafilatura/readability 가 빈 HTML 만 보기 때문에 PARSE_ERROR 발생
    # rules_json 없이 headless fetch 후 LibraryChain 폴백으로 처리
    # ==========================================================================

    {
        "host": "news.jtbc.co.kr",
        "render_mode": "headless",
        "crawl_delay_ms": 2000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        # Next.js App Router + MUI. domcontentloaded 시점에는 React 하이드레이션 미완료.
        # headless_wait_for 로 div#ijam_content 가 DOM에 나타날 때까지 대기 후 캡처.
        # author: a.author-item 은 MUI 동적 클래스 없이 안정적.
        # published_at: span 텍스트가 "입력 YYYY.MM.DD HH:MM" 형태 →
        #   XPath substring-after 로 날짜 부분만 추출.
        "rules_json": {
            "headless_wait_for": "div#ijam_content",
            "title":        {"xpath": "//meta[@property='og:title']/@content"},
            "body":         {"css": "div#ijam_content"},
            "author":       {"css": "a.author-item"},
            "published_at": {"xpath": "substring-after((//span[starts-with(., '입력 ') and not(contains(., '수정'))])[1], '입력 ')",
                             "date_format": "%Y.%m.%d %H:%M"},
            "min_body_len": 100,
        },
    },
    {
        "host": "www.ichannela.com",
        "render_mode": "static",
        "crawl_delay_ms": 1500,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        # 채널A 뉴스 — 전통적 SSR. 정적 fetch로 본문 수신 가능
        # published_at: <p class="news_view_day">날짜 <span>카테고리</span></p>
        #   → css로 꺼내면 카테고리 텍스트가 붙어 파싱 실패. XPath text()[1]로 순수 날짜만 추출.
        # author: <meta name="author"> 에 기자 이름만 깔끔하게 들어있음.
        "rules_json": {
            "title":        {"css": "div.news_title_area h1"},
            "body":         {"css": "div.news_artice_area"},
            "author":       {"xpath": "//meta[@name='author']/@content"},
            "published_at": {"xpath": "//p[@class='news_view_day']/text()[1]",
                             "date_format": "%Y-%m-%d %H:%M"},
            "min_body_len": 100,
        },
    },
    {
        "host": "biz.sbs.co.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1500,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        # 순수 CSR이나 /amp/article/{id} 에 정적 본문 존재 → amp_url 변환으로 처리
        # published_at: span.aeti_num 이 입력/수정 두 개 매칭되어 "\n" 포함 문자열이 됨
        #   → div.aeti_date_entry 로 범위를 좁혀 입력 날짜만 추출.
        # author: <strong class="aeti_title"> 에 기자명이 포함됨 ("SBS Biz 안지혜" 형태).
        "rules_json": {
            "amp_url":      {"pattern": "/article/", "replacement": "/amp/article/"},
            "title":        {"css": "h2.titleline_title_end"},
            "body":         {"css": "div.acem_text"},
            "author":       {"css": "strong.aeti_title"},
            "published_at": {"css": "div.aeti_date_entry span.aeti_num",
                             "date_format": "%Y.%m.%d %H:%M"},
            "min_body_len": 100,
        },
    },

    # ── 뉴스1 ──────────────────────────────────────────────────────────────────
    {
        "host": "www.news1.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        # Next.js Pages Router — 정적 HTML 의 __NEXT_DATA__ 에 기사 데이터 임베드.
        # 본문은 contentArrange 배열에서 type=text 항목의 content 를 이어 붙여 구성.
        "rules_json": {
            "next_data": {
                "root":             "props.pageProps.articleView",
                "title":            "title",
                "author":           "author",
                "published_at":     "published_time",
                "body_array":       "contentArrange",
                "body_type_key":    "type",
                "body_type_value":  "text",
                "body_content_key": "content",
            },
            "min_body_len": 100,
        },
    },

    # ==========================================================================
    # 페이월 → rules_enabled: False (추출 시도 자체를 건너뜀)
    # 영구 실패로 처리해 재시도 소비 방지
    # ==========================================================================

    {
        "host": "www.nytimes.com",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": False,
        "rules_json": None,
        "updated_by": "domain-analysis",
        # NYT 유료 구독 페이월 — 본문 접근 불가
    },

    # ==========================================================================
    # 정적 HTML + CSS 규칙
    # trafilatura/readability 가 광고·사이드바 노이즈로 본문을 찾지 못하는 경우.
    # 아래 셀렉터는 실제 페이지 HTML 구조 기반이며, 사이트 개편 시 재검증 필요.
    # ==========================================================================

    # ── 매일경제 (25건) ────────────────────────────────────────────────────────
    {
        "host": "www.mk.co.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1.news_ttl, h2.news_ttl"},
            "body":         {"css": "div.news_cnt_detail_wrap"},
            "author":       {"css": "div.journalist_info strong.name"},
            "published_at": {"css": "dl.journalist_info dd.date, span.registration_time",
                             "date_format": "%Y.%m.%d %H:%M"},
            "min_body_len": 100,
        },
    },

    # ── 노컷뉴스 (65건) ────────────────────────────────────────────────────────
    {
        "host": "www.nocutnews.co.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1.title, h2.title"},
            "body":         {"css": "div.article_body, div#article_body"},
            "author":       {"css": "div.writer em"},
            "published_at": {"css": "div.info span.date",
                             "date_format": "%Y-%m-%d %H:%M"},
            "min_body_len": 100,
        },
    },

    # ── 조선비즈 (70건) ────────────────────────────────────────────────────────
    {
        "host": "biz.chosun.com",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1.article-header__title, h1[class*='title']"},
            "body":         {"css": "section.article-body, div.article-body, div[class*='article-body']"},
            "author":       {"css": "span.article-byline__name"},
            "published_at": {"css": "time.article-header__time, time[class*='time']",
                             "date_format": "%Y.%m.%d %H:%M"},
            "min_body_len": 100,
        },
    },

    # ── 조선일보 (40건) ────────────────────────────────────────────────────────
    {
        "host": "www.chosun.com",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1.article-header__title, h1[class*='title']"},
            "body":         {"css": "section.article-body, div.article-body"},
            "author":       {"css": "span.article-byline__name"},
            "published_at": {"css": "time[class*='time'], span[class*='date']",
                             "date_format": "%Y.%m.%d %H:%M"},
            "min_body_len": 100,
        },
    },

    # ── 마이데일리 (105건) ─────────────────────────────────────────────────────
    {
        "host": "www.mydaily.co.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h3.tit_news, h1.tit_news, h2.tit_news"},
            "body":         {"css": "div.article_txt, div#article_txt, div.news_txt"},
            "author":       {"css": "div.article_info span.name"},
            "published_at": {"css": "div.article_info span.date",
                             "date_format": "%Y.%m.%d %H:%M"},
            "min_body_len": 100,
        },
    },

    # ── 동아사이언스 (15건) ────────────────────────────────────────────────────
    {
        "host": "www.dongascience.com",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1.article_title, div.view_top h2"},
            "body":         {"css": "div.article_txt, div.view_content, div.news_view_content"},
            "published_at": {"css": "div.article_info span.date, span.date",
                             "date_format": "%Y.%m.%d %H:%M"},
            "min_body_len": 100,
        },
    },

    # ── 전남일보 (20건) ────────────────────────────────────────────────────────
    {
        "host": "www.jndn.com",
        "render_mode": "static",
        "crawl_delay_ms": 1500,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1.article_title, div.article_head h2, h3.tit"},
            "body":         {"css": "div.article_txt, div#article_body, div.view_txt"},
            "min_body_len": 100,
        },
    },

    # ── 광주일보 (15건) ────────────────────────────────────────────────────────
    {
        "host": "www.kwangju.co.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1500,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1.article_title, div.view_title h2, h3.tit"},
            "body":         {"css": "div.article_txt, div#article_body, div.article_content"},
            "min_body_len": 100,
        },
    },

    # ── 더파워 (15건) ──────────────────────────────────────────────────────────
    {
        "host": "www.thepowernews.co.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1500,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1[class*='title'], h2[class*='title'], div.view_tit"},
            "body":         {"css": "div[class*='article'], div[class*='view_con'], div#article_body"},
            "min_body_len": 100,
        },
    },

    # ── 위클리트레이드 (10건) ──────────────────────────────────────────────────
    {
        "host": "weeklytrade.co.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1500,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1[class*='title'], h2[class*='title']"},
            "body":         {"css": "div[class*='content'], div[class*='article'], div.view_body"},
            "min_body_len": 100,
        },
    },

    # ── 스카이에디일리 모바일 (5건) ────────────────────────────────────────────
    {
        "host": "m.skyedaily.com",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1[class*='title'], h2[class*='title']"},
            "body":         {"css": "div[class*='article'], div[class*='view'], div.news_txt"},
            "min_body_len": 100,
        },
    },

    # ==========================================================================
    # 소량 실패 (5건 이하) — CSS 규칙 없이 crawl_delay + static 으로 재시도 유도
    # 규칙 추가 전 실제 HTML 구조 확인 후 업데이트 권장
    # ==========================================================================

    {"host": "www.areyou.co.kr",      "render_mode": "static", "crawl_delay_ms": 1500,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.gndomin.com",       "render_mode": "static", "crawl_delay_ms": 1500,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.worktoday.co.kr",   "render_mode": "static", "crawl_delay_ms": 1500,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.techholic.co.kr",   "render_mode": "static", "crawl_delay_ms": 1000,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.korea.kr",          "render_mode": "static", "crawl_delay_ms": 1000,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.tennispeople.kr",   "render_mode": "static", "crawl_delay_ms": 1500,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.stoo.com",          "render_mode": "static", "crawl_delay_ms": 1000,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.seoul.co.kr",       "render_mode": "static", "crawl_delay_ms": 1000,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.econotelling.com",  "render_mode": "static", "crawl_delay_ms": 1500,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "www.doctorstimes.com",  "render_mode": "static", "crawl_delay_ms": 1500,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
    {"host": "biz.newdaily.co.kr",    "render_mode": "static", "crawl_delay_ms": 1000,
     "rules_enabled": False, "rules_json": None, "updated_by": "domain-analysis"},
]

# ---------------------------------------------------------------------------

_UPSERT_SQL = text("""
    INSERT INTO t_domain
        (host, rules_json, rules_enabled, rules_version,
         render_mode, crawl_delay_ms, updated_by)
    VALUES
        (:host, :rules_json, :rules_enabled, 1,
         :render_mode, :crawl_delay_ms, :updated_by)
    ON DUPLICATE KEY UPDATE
        rules_json        = VALUES(rules_json),
        rules_enabled     = VALUES(rules_enabled),
        rules_version     = VALUES(rules_version),
        render_mode       = VALUES(render_mode),
        crawl_delay_ms    = VALUES(crawl_delay_ms),
        updated_by        = VALUES(updated_by),
        cooldown_until    = NULL,
        recent_fail_count = 0
""")


def main() -> None:
    config.validate()

    print(f"삽입 대상: {len(_RULES)}개 도메인")

    inserted = updated = 0
    with db_context() as engine:
        with engine.begin() as conn:
            for rule in _RULES:
                rules_json = rule.get("rules_json")
                result = conn.execute(_UPSERT_SQL, {
                    "host":           rule["host"],
                    "rules_json":     json.dumps(rules_json, ensure_ascii=False) if rules_json else None,
                    "rules_enabled":  rule.get("rules_enabled", True),
                    "render_mode":    rule.get("render_mode"),
                    "crawl_delay_ms": rule.get("crawl_delay_ms"),
                    "updated_by":     rule.get("updated_by", "seed"),
                })
                if result.rowcount == 1:
                    inserted += 1
                else:
                    updated += 1

    print(f"완료: INSERT {inserted}건, UPDATE {updated}건 (총 {inserted + updated}건)")


if __name__ == "__main__":
    main()
