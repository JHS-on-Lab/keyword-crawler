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
                "press":        "result.itemName",
            },
            "min_body_len": 5,
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
        "rules_enabled": False,
        "rules_json": None,
        "updated_by": "domain-analysis",
        # JTBC News — React SPA. 정적 fetch 시 빈 <div id="root"> 만 수신
    },
    {
        "host": "www.ichannela.com",
        "render_mode": "headless",
        "crawl_delay_ms": 2000,
        "rules_enabled": False,
        "rules_json": None,
        "updated_by": "domain-analysis",
        # 채널A 뉴스 — JavaScript 렌더링
    },
    {
        "host": "biz.sbs.co.kr",
        "render_mode": "headless",
        "crawl_delay_ms": 1500,
        "rules_enabled": False,
        "rules_json": None,
        "updated_by": "domain-analysis",
        # SBS Biz — React 기반 SPA. 정적 HTML 에 본문 없음
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

    # ── 뉴스1 (15건) ───────────────────────────────────────────────────────────
    {
        "host": "www.news1.kr",
        "render_mode": "static",
        "crawl_delay_ms": 1000,
        "rules_enabled": True,
        "updated_by": "domain-analysis",
        "rules_json": {
            "title":        {"css": "h1.title, div.detail_tit h2"},
            "body":         {"css": "div.detail_body, article.detail_article, div.news_article"},
            "author":       {"css": "div.detail_info span.name"},
            "published_at": {"css": "div.detail_info span.date",
                             "date_format": "%Y-%m-%d %H:%M"},
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
