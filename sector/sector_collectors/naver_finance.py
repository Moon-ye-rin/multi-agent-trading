"""
네이버 증권 크롤링 모듈
목표주가·투자의견 지표 데이터를 수집합니다.
(구현 미완성, consensus_test.py 파일에서 한경컨센서스 크롤링 확인 가능)
"""
import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger("naver_finance")

REQUEST_DELAY = float(os.getenv("NAVER_REQUEST_DELAY", "1.0"))
MAX_RETRIES   = int(os.getenv("NAVER_MAX_RETRIES", "3"))
TIMEOUT       = int(os.getenv("NAVER_TIMEOUT", "10"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://finance.naver.com/",
}


def _fetch(url: str) -> Optional[BeautifulSoup]:
    """HTTP GET + BeautifulSoup 파싱 (재시도 포함)"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            resp.encoding = "euc-kr"
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            logger.warning(f"  요청 실패 ({attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_DELAY * attempt)
    return None


def _parse_number(text: str) -> Optional[float]:
    """문자열에서 숫자 추출 (쉼표·단위 제거)"""
    if not text:
        return None
    cleaned = text.replace(",", "").replace("원", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


# ── 1. 현재 주가 및 기본 정보 ─────────────────────────────────────
def get_current_price(ticker: str) -> dict:
    """
    현재 주가, 전일 대비 수집

    Returns:
        { current_price, change, change_pct, volume, market_cap_100m }
    """
    # analyst.naver는 404로 서비스 종료됨 → main.naver로 변경
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    logger.info(f"[네이버] 현재가 조회: {url}")
    soup = _fetch(url)
    if not soup:
        return {"error": "현재가 조회 실패"}

    result = {}
    try:
        # 현재가
        price_tag = soup.select_one("p.no_today span.blind")
        result["current_price"] = _parse_number(price_tag.text) if price_tag else None

        # 등락
        change_tag = soup.select_one("p.no_today em span.blind")
        result["change"] = _parse_number(change_tag.text) if change_tag else None

        # 등락률
        pct_tags = soup.select("p.no_today em")
        if len(pct_tags) >= 2:
            pct_blind = pct_tags[1].select("span.blind")
            result["change_pct"] = _parse_number(pct_blind[-1].text) if pct_blind else None

        # 거래량
        vol_tag = soup.select_one("table.no_info td:nth-child(3) em")
        result["volume"] = _parse_number(vol_tag.text) if vol_tag else None

        # 시가총액 (억)
        cap_tag = soup.select_one("table.no_info td:nth-child(5) em")
        if cap_tag:
            cap_val = _parse_number(cap_tag.text)
            result["market_cap_100m"] = cap_val  # 네이버는 억원 단위 제공

    except Exception as e:
        logger.error(f"[네이버] 현재가 파싱 오류: {e}")

    time.sleep(REQUEST_DELAY)
    return result


# ── 2. 목표주가·투자의견 (애널리스트 컨센서스) ──────────────────────
def get_analyst_opinions(ticker: str) -> dict:
    """
    네이버 증권 종목분석 데이터를 수집합니다.
    모바일 API의 404 에러를 피하기 위해 PC 리서치 페이지와 메인 컨센서스 데이터를 활용합니다.
    """
    # [변경] 모바일 API 대신 PC 버전의 메인 페이지 컨센서스 영역 활용
    main_url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    research_url = f"https://finance.naver.com/research/company_list.naver?keyword=&searchType=itemCode&itemCode={ticker}"
    
    logger.info(f"[네이버] 애널리스트 의견 조회 시작: {ticker}")
    
    reports = []
    result = {
        "reports": [],
        "avg_target_price": {"all": None, "1m": None, "3m": None},
        "buy_ratio": {"all": None, "1m": None, "3m": None},
        "target_price_trend": "데이터 부족",
        "report_count": {"all": 0, "1m": 0, "3m": 0},
    }

    # 1. 최근 리포트 목록 수집 (PC 리서치 페이지)
    soup_res = _fetch(research_url)
    if soup_res:
        # 리포트 테이블 행 추출 (상위 20개)
        rows = soup_res.select("table.type_1 tr")
        for row in rows:
            tds = row.select("td")
            if len(tds) < 5: continue
            
            # 종목 리서치 페이지 구조상 투자의견과 목표주가가 제목에 섞여 있는 경우가 많음
            # 여기서는 안정적인 리포트 날짜와 증권사 정보를 우선 수집
            date = tds[4].get_text(strip=True)
            firm = tds[2].get_text(strip=True)
            title = tds[1].get_text(strip=True)
            
            # 제목에서 숫자(목표가) 추출 시도 (정교한 파싱 필요 시 regex 사용)
            reports.append({
                "date": date,
                "firm": firm,
                "opinion": "분석중", # 리서치 리스트에는 의견이 텍스트로만 존재
                "target_price": 0.0, 
                "title": title
            })
            if len(reports) >= 20: break
    
    # 2. 요약 컨센서스 수집 (PC 메인 페이지 aside_invest_info 영역)
    # 이 영역은 PC 페이지에서 '투자의견 및 목표주가' 섹션으로 고정되어 있어 매우 안정적입니다.
    soup_main = _fetch(main_url)
    if soup_main:
        try:
            consen_section = soup_main.select_one(".aside_invest_info")
            if consen_section:
                # 목표주가 평균 (em 태그 내의 숫자)
                tp_tag = consen_section.select_one("table tr:nth-of-type(2) em")
                avg_tp = _parse_number(tp_tag.text) if tp_tag else None
                
                # 투자의견 (예: 4.00매수)
                opinion_tag = consen_section.select_one("table tr:nth-of-type(1) em")
                opinion_text = opinion_tag.text if opinion_tag else "N/A"
                
                result["avg_target_price"]["all"] = avg_tp
                result["target_price_trend"] = "컨센서스 기반"
                
                # 리포트 개수 (보통 '62'건 등의 형태로 표시됨)
                count_tag = consen_section.select_one(".comment em")
                count_val = int(_parse_number(count_tag.text)) if count_tag else 0
                result["report_count"]["all"] = count_val
        except Exception as e:
            logger.error(f"[네이버] 컨센서스 요약 파싱 오류: {e}")

    result["reports"] = reports
    logger.info(f"[네이버] 수집 완료 (리포트 {len(reports)}건 / 요약 목표가 {result['avg_target_price']['all']})")
    
    return result


# ── 3. 52주 최고·최저 및 추가 시장 정보 ──────────────────────────
def get_market_info(ticker: str) -> dict:
    """
    52주 최고·최저가, 외국인 보유율 등 보조 지표

    Returns:
        { "52w_high", "52w_low", "52w_position_pct",
          "foreign_ownership_pct", "per", "pbr", "eps" }
    """
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    logger.info(f"[네이버] 시장 정보 조회: {url}")
    soup = _fetch(url)
    if not soup:
        return {"error": "시장 정보 조회 실패"}

    result = {}
    try:
        info_table = soup.select("table.no_info td em")
        values = [_parse_number(em.get_text(strip=True)) for em in info_table]

        # 네이버 증권 table.no_info 컬럼 순서:
        # 0:전일종가, 1:시가, 2:거래량, 3:거래대금, 4:시가총액, 5:상장주식수
        # (구조는 JS 렌더링에 따라 달라질 수 있으므로 보조적으로 활용)

        # 52주 최고·최저 별도 파싱
        w52_tags = soup.select("div.rate_info table td")
        for td in w52_tags:
            label = td.get_text(strip=True)
            if "52" in label:
                nums = [_parse_number(s.get_text()) for s in td.select("em") if s.get_text().strip()]
                if len(nums) >= 2:
                    result["52w_high"] = nums[0]
                    result["52w_low"]  = nums[1]

        # 현재 주가 기준 52주 위치 (%)
        price_tag = soup.select_one("p.no_today span.blind")
        current = _parse_number(price_tag.text) if price_tag else None
        if current and result.get("52w_high") and result.get("52w_low"):
            rang = result["52w_high"] - result["52w_low"]
            result["52w_position_pct"] = round((current - result["52w_low"]) / rang * 100, 1) if rang > 0 else None

        # 외국인 보유율 (별도 URL)
        result["current_price"] = current

    except Exception as e:
        logger.error(f"[네이버] 시장 정보 파싱 오류: {e}")

    # 외국인 보유율
    try:
        own_url  = f"https://finance.naver.com/item/frgn.nhn?code={ticker}"
        own_soup = _fetch(own_url)
        if own_soup:
            own_tag = own_soup.select_one("table.type_1 td em")
            result["foreign_ownership_pct"] = _parse_number(own_tag.text) if own_tag else None
    except Exception as e:
        logger.warning(f"[네이버] 외국인 보유율 조회 실패: {e}")
        result["foreign_ownership_pct"] = None

    time.sleep(REQUEST_DELAY)
    return result


# ── 통합 수집 함수 ──────────────────────────────────────────────
def get_naver_finance_data(ticker: str) -> dict:
    """
    네이버 증권 전체 데이터 수집 (통합 진입점)

    Returns:
        dict: {
            "current_price_info": { ... },
            "analyst_opinions":   { ... },
            "market_info":        { ... },
            "as_of":              "YYYY-MM-DD HH:MM",
        }
    """
    logger.info(f"[네이버] 전체 데이터 수집 시작: {ticker}")
    return {
        "current_price_info": get_current_price(ticker),
        "analyst_opinions":   get_analyst_opinions(ticker),
        "market_info":        get_market_info(ticker),
        "as_of":              datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
