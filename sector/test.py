# sector/naver_company_report_crawler.py
import sys
import io
import os
import json
import time
from datetime import datetime, timedelta
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_URL   = "https://finance.naver.com"
LIST_URL   = "https://finance.naver.com/research/company_list.naver"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

SKIP_CLASSES  = {"blank_07", "blank_08", "blank_09", "division_line", "division_line_1"}
BUY_KEYWORDS  = {"매수", "Buy", "BUY", "Strong Buy", "강력매수"}
SELL_KEYWORDS = {"매도", "Sell", "SELL"}
HOLD_KEYWORDS = {"중립", "보유", "Hold", "HOLD", "Neutral"}


# ── Selenium 드라이버 ──────────────────────────────────────────
def get_driver() -> webdriver.Chrome:
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


def wait_table(driver: webdriver.Chrome, timeout: int = 10) -> None:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "table.type_1 tbody tr")
            )
        )
    except Exception:
        pass
    time.sleep(1.0)


# ── STEP 1. 검색 수행 ──────────────────────────────────────────
def search_keyword(driver: webdriver.Chrome, target_name: str) -> str:
    """
    검색창에 종목명 입력 → 검색 버튼 클릭 → 검색 결과 URL 반환
    """
    print(f"  🔍 검색창에 '{target_name}' 입력 중...")

    keyword_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "keyword"))
    )
    keyword_input.clear()
    keyword_input.send_keys(target_name)
    time.sleep(0.5)

    search_btn = driver.find_element(
        By.CSS_SELECTOR, "input[type='image'][alt='검색']"
    )
    search_btn.click()
    wait_table(driver)

    search_url = driver.current_url
    print(f"  ✅ 검색 완료 → {search_url}\n")
    return search_url


# ── STEP 2. 목록 페이지 파싱 ──────────────────────────────────
def parse_list_page(html: str, target_name: str) -> tuple[list[dict], bool]:
    """
    검색 결과에서 target_name 행 추출.

    Returns:
        (rows, stop_flag)
        stop_flag=True  → 3개월 초과 날짜 발견 → 크롤링 종료 신호
    """
    soup      = BeautifulSoup(html, "lxml")
    found     = []
    stop_flag = False
    cutoff    = datetime.today() - timedelta(days=90)   # 3개월 기준

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

        # 종목명
        stock_tag  = tds[0].select_one("a")
        stock_name = (
            stock_tag.get_text(strip=True)
            if stock_tag
            else tds[0].get_text(strip=True)
        )

        # 날짜 파싱 (타겟 무관하게 날짜를 먼저 확인)
        date_text = tds[4].get_text(strip=True) if len(tds) > 4 else ""
        date_obj  = None
        for fmt in ("%y.%m.%d", "%Y.%m.%d"):
            try:
                date_obj = datetime.strptime(date_text, fmt)
                break
            except ValueError:
                continue

        # 3개월 초과 날짜 발견 시 종료 신호
        if date_obj and date_obj < cutoff:
            stop_flag = True
            break

        # 타겟 종목만 수집
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

        firm = tds[2].get_text(strip=True) if len(tds) > 2 else ""

        found.append({
            "stock_name":   stock_name,
            "title":        title,
            "firm":         firm,
            "date":         date_text,
            "_date_obj":    date_obj,
            "detail_url":   detail_url,
            "target_price": None,
            "opinion":      None,
        })

    return found, stop_flag


# ── STEP 3. 세부 페이지에서 목표주가·투자의견 파싱 ─────────────
def parse_detail_page(html: str) -> tuple[Optional[float], Optional[str]]:
    soup         = BeautifulSoup(html, "lxml")
    target_price = None
    opinion      = None

    # 방법 1: .coinfo_spec 테이블
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

    # 방법 3: em·strong 태그
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


def _parse_price(text: str) -> Optional[float]:
    cleaned = text.replace(",", "").replace("원", "").strip()
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


# ── STEP 4. 전체 수집 ─────────────────────────────────────────
def crawl(target_name: str) -> dict:
    """
    검색 후 페이지 제한 없이 순회.
    3개월 초과 날짜 발견 시 즉시 종료.
    """
    print(f"\n🔎 [{target_name}] 종목분석 리포트 수집 시작 (3개월 이내)\n")

    driver   = get_driver()
    all_rows: list[dict] = []

    try:
        # 초기 접속 + 검색
        driver.get(LIST_URL)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "keyword"))
        )
        time.sleep(1.0)

        search_url = search_keyword(driver, target_name)

        page = 1
        while True:
            # 페이지 URL 생성
            if page == 1:
                page_url = search_url
            else:
                page_url = (
                    f"{search_url}&page={page}"
                    if "page=" not in search_url
                    else search_url.replace(f"page={page-1}", f"page={page}")
                )

            print(f"  📄 페이지 {page} 파싱 중...")
            driver.get(page_url)
            wait_table(driver)

            rows, stop = parse_list_page(driver.page_source, target_name)

            if not rows and stop:
                print(f"     → 3개월 초과 날짜 감지 → 수집 종료")
                break

            if not rows:
                print(f"     → [{target_name}] 0건 → 수집 종료")
                break

            print(f"     → [{target_name}] {len(rows)}건 발견")

            # 세부 페이지 접속
            current_list_url = driver.current_url

            for j, row in enumerate(rows, start=1):
                print(
                    f"       [{j}/{len(rows)}] {row['firm']} "
                    f"({row['date']}) 수집 중..."
                )
                try:
                    driver.get(row["detail_url"])
                    time.sleep(1.0)

                    tp, op = parse_detail_page(driver.page_source)
                    row["target_price"] = tp
                    row["opinion"]      = op

                    tp_str = f"{tp:,.0f}원" if tp else "N/A"
                    op_str = op if op else "N/A"
                    print(f"         목표가: {tp_str} | 의견: {op_str}")

                except Exception as e:
                    print(f"         ⚠️  세부 페이지 오류: {e}")

                driver.get(current_list_url)
                wait_table(driver)

            all_rows.extend(rows)

            if stop:
                print(f"\n  ⛔ 3개월 초과 날짜 감지 → 수집 종료")
                break

            page += 1

    finally:
        driver.quit()

    print(f"\n  ✅ 수집 완료 — 총 {len(all_rows)}건\n")
    return _aggregate(all_rows, target_name)


# ── STEP 5. 집계 ──────────────────────────────────────────────
def _aggregate(rows: list[dict], target_name: str) -> dict:
    today_dt = datetime.today()

    def within(r: dict, days: int) -> bool:
        d = r.get("_date_obj")
        return (today_dt - d).days <= days if d else False

    rows_1m = [r for r in rows if within(r, 30)]
    rows_3m = rows   # 수집 자체가 3개월 이내만 → 전체 = 3개월

    def avg_tp(rlist: list) -> Optional[float]:
        prices = [r["target_price"] for r in rlist if r.get("target_price")]
        return round(sum(prices) / len(prices), 0) if prices else None

    def buy_ratio(rlist: list) -> Optional[float]:
        ops = [r.get("opinion") for r in rlist if r.get("opinion")]
        if not ops:
            return None
        buy_cnt = sum(1 for op in ops if any(kw in op for kw in BUY_KEYWORDS))
        return round(buy_cnt / len(ops) * 100, 1)

    # 목표주가 추세: 1개월 평균 vs 1~3개월 전 평균
    rows_prev = [r for r in rows_3m if not within(r, 30)]
    avg_1m    = avg_tp(rows_1m)
    avg_prev  = avg_tp(rows_prev)

    if avg_1m and avg_prev and avg_prev != 0:
        diff  = (avg_1m - avg_prev) / avg_prev * 100
        trend = "상향" if diff >= 2 else ("하향" if diff <= -2 else "유지")
    elif avg_1m:
        trend = "데이터 부족"
    else:
        trend = "N/A"

    return {
        "analyst_opinion": {
            "avg_target_price": {
                "1m": avg_1m,
                "3m": avg_tp(rows_3m),
            },
            "target_price_gap_rate": None,
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
        },
        "stock_name": target_name,
        "as_of":      datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ── 출력 ──────────────────────────────────────────────────────
def print_result(result: dict) -> None:
    SEP = "=" * 60
    print(f"\n{SEP}")
    print(f"  📊 [{result['stock_name']}] 수집 결과")
    print(f"  수집 시각: {result['as_of']}")
    print(SEP)
    print(json.dumps({"analyst_opinion": result["analyst_opinion"]},
                     ensure_ascii=False, indent=2))
    print(SEP)


def save_json(result: dict) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = result["stock_name"].replace(" ", "_")
    path = os.path.join(OUTPUT_DIR, f"analyst_opinion_{name}_{ts}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  💾 JSON 저장: {path}")
    return path


# ── 실행 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    TARGET_NAME = "삼성전자"

    result = crawl(target_name=TARGET_NAME)
    print_result(result)
    #save_json(result)