import sys, io, time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_URL = "https://finance.naver.com"
LIST_URL = "https://finance.naver.com/research/market_info_list.naver"
SKIP_CLASSES = {"blank_07", "blank_08", "blank_09", "division_line", "division_line_1"}


def get_driver():
    options = Options()
    options.add_argument("--headless")           # 브라우저 창 숨김
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def parse_reports(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    reports = []

    for tr in soup.select("table.type_1 tbody tr"):
        if tr.select("th"):
            continue

        tds = tr.select("td")
        if not tds:
            continue

        # 구분선·여백 행 스킵
        if len(tds) == 1:
            td_class = set(tds[0].get("class", []))
            if td_class & SKIP_CLASSES:
                continue

        if len(tds) < 4:
            continue

        title_tag = tds[0].select_one("a")
        if not title_tag or not title_tag.get_text(strip=True):
            continue

        title      = title_tag.get_text(strip=True)
        detail_href = title_tag.get("href", "")
        detail_url  = (
            BASE_URL + "/research/" + detail_href
            if detail_href and not detail_href.startswith("http")
            else detail_href
        )

        firm       = tds[1].get_text(strip=True)
        attach_tag = tds[2].select_one("a[href]")
        attach_url = attach_tag.get("href") if attach_tag else None
        date       = tds[3].get_text(strip=True)
        views      = tds[4].get_text(strip=True) if len(tds) >= 5 else ""

        reports.append({
            "title":      title,
            "firm":       firm,
            "attach_url": attach_url,
            "date":       date,
            "views":      views,
            "detail_url": detail_url,
        })

    return reports


def crawl(max_pages: int = 3) -> list[dict]:
    print(f"🔎 네이버 증권 시황정보 크롤링 시작 (최대 {max_pages}페이지)\n")
    driver      = get_driver()
    all_reports = []

    try:
        for page in range(1, max_pages + 1):
            url = f"{LIST_URL}?page={page}"
            print(f"  📄 페이지 {page} 로딩 중: {url}")
            driver.get(url)

            # table.type_1 tbody tr 이 로딩될 때까지 대기 (최대 10초)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "table.type_1 tbody tr")
                    )
                )
            except Exception:
                print(f"     ⚠️  테이블 로딩 타임아웃 — 현재 HTML로 파싱 시도")

            time.sleep(1)   # 추가 렌더링 대기

            reports = parse_reports(driver.page_source)
            all_reports.extend(reports)
            print(f"     → {len(reports)}건 수집")

    finally:
        driver.quit()

    return all_reports


def print_reports(reports: list[dict]) -> None:
    SEP  = "=" * 110
    SEP2 = "-" * 110

    print(f"\n{SEP}")
    print(f"  총 {len(reports)}건 수집 완료")
    print(SEP)
    print(
        f"  {'번호':>4} | {'작성일':<10} | {'증권사':<14} | {'조회':>5} | "
        f"{'제목':<38} | 첨부PDF"
    )
    print(SEP2)

    for i, r in enumerate(reports, start=1):
        title_short = r["title"][:36] + ".." if len(r["title"]) > 38 else r["title"]
        attach_str  = r["attach_url"] if r["attach_url"] else "없음"
        print(
            f"  {i:>4} | {r['date']:<10} | {r['firm']:<14} | {r['views']:>5} | "
            f"{title_short:<38} | {attach_str}"
        )

    print(SEP)


if __name__ == "__main__":
    reports = crawl(max_pages=3)
    if reports:
        print_reports(reports)
    else:
        print("❌ 수집된 데이터가 없습니다.")