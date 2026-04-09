"""
네이버 증권 + pykrx 통합 수집 모듈

수집 방식:
  current_price_info : pykrx (OHLCV, 시가총액)
  analyst_opinion    : 네이버 종목분석 Selenium 크롤링 (목표주가·투자의견)
"""
import os
import time
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from pykrx import stock as pykrx_stock
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger("naver_finance")

REQUEST_DELAY = float(os.getenv("NAVER_REQUEST_DELAY", "1.0"))
TIMEOUT       = int(os.getenv("NAVER_TIMEOUT", "10"))

BASE_URL = "https://finance.naver.com"
LIST_URL = "https://finance.naver.com/research/company_list.naver"

SKIP_CLASSES  = {"blank_07", "blank_08", "blank_09", "division_line", "division_line_1"}
BUY_KEYWORDS  = {"매수", "Buy", "BUY", "Strong Buy", "강력매수"}
SELL_KEYWORDS = {"매도", "Sell", "SELL"}
HOLD_KEYWORDS = {"중립", "보유", "Hold", "HOLD", "Neutral"}


# ══════════════════════════════════════════════════════════════
# 공통 유틸
# ══════════════════════════════════════════════════════════════

def _today() -> str:
    return datetime.today().strftime("%Y%m%d")

def _date_before(days: int) -> str:
    return (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")

def _parse_price(text: str) -> Optional[float]:
    cleaned = text.replace(",", "").replace("원", "").strip()
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


# ══════════════════════════════════════════════════════════════
# 1. 현재가 및 당일 시세 (pykrx)
# ══════════════════════════════════════════════════════════════

def get_current_price(ticker: str) -> dict:
    """
    당일 시세 수집 (pykrx)

    Returns:
        current_price   : 현재가 (원)
        change          : 전일 대비 (원)
        change_pct      : 등락률 (%)
        volume          : 거래량
        market_cap_100m : 시가총액 (억원)
    """
    logger.info(f"[pykrx] 현재가 조회: {ticker}")
    result: dict = {
        "current_price":   None,
        "change":          None,
        "change_pct":      None,
        "volume":          None,
        "market_cap_100m": None,
    }

    try:
        df = pykrx_stock.get_market_ohlcv(_date_before(7), _today(), ticker)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            prev   = df.iloc[-2] if len(df) >= 2 else None

            result["current_price"] = float(latest["종가"])
            result["volume"]        = int(latest["거래량"])

            if prev is not None:
                change     = float(latest["종가"]) - float(prev["종가"])
                change_pct = (
                    round(change / float(prev["종가"]) * 100, 2)
                    if float(prev["종가"]) else None
                )
                result["change"]     = round(change, 0)
                result["change_pct"] = change_pct
        else:
            logger.warning(f"[pykrx] OHLCV 데이터 없음: {ticker}")

    except Exception as e:
        logger.error(f"[pykrx] 현재가 조회 실패: {e}")

    try:
        df_cap = pykrx_stock.get_market_cap(_today(), _today(), ticker)
        if df_cap is not None and not df_cap.empty:
            result["market_cap_100m"] = round(
                float(df_cap["시가총액"].iloc[-1]) / 1e8, 1
            )
    except Exception as e:
        logger.warning(f"[pykrx] 시가총액 조회 실패: {e}")

    logger.info(
        f"[pykrx] 현재가 완료 | "
        f"{result.get('current_price')}원 ({result.get('change_pct')}%)"
    )
    return result


# ══════════════════════════════════════════════════════════════
# 2. 애널리스트 의견 (네이버 종목분석 Selenium 크롤링)
# ══════════════════════════════════════════════════════════════

def _get_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _wait_table(driver, timeout: int = 10) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "table.type_1 tbody tr")
            )
        )
    except Exception:
        pass
    time.sleep(1.0)


def _search_keyword(driver, target_name: str) -> str:
    """검색창에 종목명 입력 → 검색 버튼 클릭 → 결과 URL 반환"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    keyword_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "keyword"))
    )
    keyword_input.clear()
    keyword_input.send_keys(target_name)
    time.sleep(0.5)

    driver.find_element(
        By.CSS_SELECTOR, "input[type='image'][alt='검색']"
    ).click()
    _wait_table(driver)

    return driver.current_url


def _parse_list_page(html: str, target_name: str) -> tuple[list[dict], bool]:
    """
    목록 페이지 파싱.
    Returns: (rows, stop_flag)
      stop_flag=True → 3개월 초과 날짜 발견 → 수집 종료
    """
    soup   = BeautifulSoup(html, "lxml")
    found  = []
    stop   = False
    cutoff = datetime.today() - timedelta(days=90)

    for tr in soup.select("table.type_1 tbody tr"):
        if tr.select("th"):
            continue

        tds = tr.select("td")
        if not tds:
            continue

        if len(tds) == 1:
            if set(tds[0].get("class", [])) & SKIP_CLASSES:
                continue

        if len(tds) < 4:
            continue

        # 날짜 먼저 확인 → 3개월 초과 시 종료
        date_text = tds[4].get_text(strip=True) if len(tds) > 4 else ""
        date_obj  = None
        for fmt in ("%y.%m.%d", "%Y.%m.%d"):
            try:
                date_obj = datetime.strptime(date_text, fmt)
                break
            except ValueError:
                continue

        if date_obj and date_obj < cutoff:
            stop = True
            break

        # 종목명 필터
        stock_tag  = tds[0].select_one("a")
        stock_name = (
            stock_tag.get_text(strip=True) if stock_tag
            else tds[0].get_text(strip=True)
        )
        if stock_name != target_name:
            continue

        # 세부 페이지 URL
        title_tag   = tds[1].select_one("a")
        title       = title_tag.get_text(strip=True) if title_tag else ""
        detail_href = title_tag.get("href", "") if title_tag else ""
        if not detail_href:
            continue

        detail_url = (
            BASE_URL + "/research/" + detail_href
            if not detail_href.startswith("http")
            else detail_href
        )

        found.append({
            "firm":         tds[2].get_text(strip=True) if len(tds) > 2 else "",
            "title":        title,
            "date":         date_text,
            "_date_obj":    date_obj,
            "detail_url":   detail_url,
            "target_price": None,
            "opinion":      None,
        })

    return found, stop


def _parse_detail_page(html: str) -> tuple[Optional[float], Optional[str]]:
    """세부 페이지에서 목표주가·투자의견 파싱"""
    soup         = BeautifulSoup(html, "lxml")
    target_price = None
    opinion      = None

    # 방법 1: .coinfo_spec
    spec = soup.select_one(".coinfo_spec")
    if spec:
        for row in spec.select("tr"):
            tds = row.select("td, th")
            for i, td in enumerate(tds):
                text = td.get_text(strip=True)
                if any(kw in text for kw in [*BUY_KEYWORDS, *SELL_KEYWORDS, *HOLD_KEYWORDS]):
                    if opinion is None:
                        opinion = text
                if ("목표" in text or "Target" in text.lower()) and i + 1 < len(tds):
                    tp_val = _parse_price(tds[i + 1].get_text(strip=True))
                    if tp_val:
                        target_price = tp_val

    # 방법 2: table.view_info
    if target_price is None or opinion is None:
        for td in soup.select("table.view_info td"):
            text = td.get_text(strip=True)
            if target_price is None:
                tp_val = _parse_price(text)
                if tp_val and tp_val > 1000:
                    target_price = tp_val
            if opinion is None:
                if any(kw in text for kw in [*BUY_KEYWORDS, *SELL_KEYWORDS, *HOLD_KEYWORDS]):
                    opinion = text

    # 방법 3: em·strong
    if target_price is None or opinion is None:
        for tag in soup.select("em, strong, .num"):
            text = tag.get_text(strip=True)
            if target_price is None:
                tp_val = _parse_price(text)
                if tp_val and tp_val > 1000:
                    target_price = tp_val
            if opinion is None:
                if any(kw in text for kw in [*BUY_KEYWORDS, *SELL_KEYWORDS, *HOLD_KEYWORDS]):
                    opinion = text

    return target_price, opinion


def _crawl_analyst(target_name: str) -> list[dict]:
    """Selenium으로 종목분석 페이지 크롤링 → 3개월 이내 전체 수집"""
    logger.info(f"[네이버] 애널리스트 크롤링 시작: {target_name}")
    driver   = _get_driver()
    all_rows: list[dict] = []

    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver.get(LIST_URL)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "keyword"))
        )
        time.sleep(1.0)

        search_url = _search_keyword(driver, target_name)
        logger.info(f"[네이버] 검색 완료: {search_url}")

        page = 1
        while True:
            page_url = (
                search_url if page == 1
                else (
                    f"{search_url}&page={page}"
                    if "page=" not in search_url
                    else search_url.replace(f"page={page-1}", f"page={page}")
                )
            )

            logger.info(f"[네이버] 페이지 {page} 파싱 중...")
            driver.get(page_url)
            _wait_table(driver)

            rows, stop = _parse_list_page(driver.page_source, target_name)

            if not rows and stop:
                logger.info("[네이버] 3개월 초과 → 수집 종료")
                break
            if not rows:
                logger.info("[네이버] 결과 없음 → 수집 종료")
                break

            logger.info(f"[네이버] {len(rows)}건 발견")
            current_list_url = driver.current_url

            for j, row in enumerate(rows, start=1):
                logger.info(
                    f"  [{j}/{len(rows)}] {row['firm']} ({row['date']}) 세부 수집..."
                )
                try:
                    driver.get(row["detail_url"])
                    time.sleep(1.0)
                    tp, op = _parse_detail_page(driver.page_source)
                    row["target_price"] = tp
                    row["opinion"]      = op
                    logger.info(
                        f"    목표가: {f'{tp:,.0f}원' if tp else 'N/A'} | "
                        f"의견: {op or 'N/A'}"
                    )
                except Exception as e:
                    logger.warning(f"  세부 페이지 오류: {e}")

                driver.get(current_list_url)
                _wait_table(driver)

            all_rows.extend(rows)

            if stop:
                logger.info("[네이버] 3개월 초과 감지 → 수집 종료")
                break

            page += 1

    finally:
        driver.quit()

    logger.info(f"[네이버] 크롤링 완료 — 총 {len(all_rows)}건")
    return all_rows


def _aggregate_analyst(rows: list[dict], ticker: str) -> dict:
    """수집 결과 집계 → analyst_opinion JSON 구조 생성"""
    today_dt = datetime.today()

    def within(r: dict, days: int) -> bool:
        d = r.get("_date_obj")
        return (today_dt - d).days <= days if d else False

    rows_1m = [r for r in rows if within(r, 30)]
    rows_3m = rows   # 수집 자체가 3개월 이내

    def avg_tp(rlist: list) -> Optional[float]:
        prices = [r["target_price"] for r in rlist if r.get("target_price")]
        return round(sum(prices) / len(prices), 0) if prices else None

    def buy_ratio(rlist: list) -> Optional[float]:
        ops = [r.get("opinion") for r in rlist if r.get("opinion")]
        if not ops:
            return None
        buy_cnt = sum(1 for op in ops if any(kw in op for kw in BUY_KEYWORDS))
        return round(buy_cnt / len(ops) * 100, 1)

    avg_1m   = avg_tp(rows_1m)
    avg_prev = avg_tp([r for r in rows_3m if not within(r, 30)])

    # 목표주가 추세: 1개월 vs 1~3개월 전
    if avg_1m and avg_prev and avg_prev != 0:
        diff  = (avg_1m - avg_prev) / avg_prev * 100
        trend = "상향" if diff >= 2 else ("하향" if diff <= -2 else "유지")
    elif avg_1m:
        trend = "데이터 부족"
    else:
        trend = "N/A"

    # 괴리율 (현재가 대비 1개월 평균 목표주가)
    gap_rate = None
    try:
        df = pykrx_stock.get_market_ohlcv(_date_before(7), _today(), ticker)
        if df is not None and not df.empty and avg_1m:
            current  = float(df["종가"].iloc[-1])
            gap_rate = round((avg_1m - current) / current * 100, 1) if current else None
    except Exception as e:
        logger.warning(f"[pykrx] 괴리율 계산 실패: {e}")

    return {
        "avg_target_price": {
            "1m": avg_1m,
            "3m": avg_tp(rows_3m),
        },
        "target_price_gap_rate": gap_rate,
        "target_price_trend":    trend,
        "buy_ratio": {
            "1m": buy_ratio(rows_1m),
            "3m": buy_ratio(rows_3m),
        },
        "report_count": {
            "1m": len(rows_1m),
            "3m": len(rows_3m),
        },
        "source": "naver_crawl",
        "note":   "크롤링 실패 시 DART 공시 목표주가로 대체 시도. 대체도 실패 시 null 처리 후 논거 생략",
    }


def _empty_analyst() -> dict:
    return {
        "avg_target_price":      {"1m": None, "3m": None},
        "target_price_gap_rate": None,
        "target_price_trend":    "N/A",
        "buy_ratio":             {"1m": None, "3m": None},
        "report_count":          {"1m": 0,    "3m": 0},
        "source":                "naver_crawl",
        "note":                  "크롤링 실패 시 DART 공시 목표주가로 대체 시도. 대체도 실패 시 null 처리 후 논거 생략",
    }


def get_analyst_opinions(ticker: str, stock_name: str) -> dict:
    """
    애널리스트 의견 수집 통합 진입점.

    Args:
        ticker:     종목 코드 (예: "005930")
        stock_name: 종목명   (예: "삼성전자")
    """
    try:
        rows = _crawl_analyst(stock_name)
        if not rows:
            logger.warning("[네이버] 수집 결과 없음 → null 처리")
            return _empty_analyst()
        return _aggregate_analyst(rows, ticker)
    except Exception as e:
        logger.error(f"[네이버] 애널리스트 수집 실패: {e}")
        return _empty_analyst()


# ══════════════════════════════════════════════════════════════
# 3. 통합 수집 진입점
# ══════════════════════════════════════════════════════════════

def get_naver_finance_data(ticker: str, stock_name: str) -> dict:
    """
    전체 데이터 수집 통합 진입점.

    Args:
        ticker:     종목 코드 (예: "005930")
        stock_name: 종목명   (예: "삼성전자")

    Returns:
        {
            "current_price_info": {
                current_price, change, change_pct,
                volume, market_cap_100m
            },
            "analyst_opinion": {
                avg_target_price, target_price_gap_rate,
                target_price_trend, buy_ratio,
                report_count, source, note
            },
            "as_of": "YYYY-MM-DD HH:MM"
        }
    """
    logger.info(f"[naver_finance] 전체 수집 시작: {stock_name} ({ticker})")
    return {
        "current_price_info": get_current_price(ticker),
        "analyst_opinion":    get_analyst_opinions(ticker, stock_name),
        "as_of":              datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
