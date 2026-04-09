import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sys
import io

# 1. 출력 스트림 인코딩 설정 (윈도우 터미널 한글 깨짐 방지)
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

def get_hankyung_opinions(ticker: str, days: int = 90):
    today = datetime.today()
    start_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    
    base_url = "https://consensus.hankyung.com/analysis/list?skinType=business"
    
    params = {
        "skinType": "business",
        "sdate": start_date,
        "edate": end_date,
        "search_text": ticker,
        "now_page": 1
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://consensus.hankyung.com/"
    }

    print(f"🔎 [{ticker}] 한경컨센서스 검색 시작: {start_date} ~ {end_date}")

    try:
        resp = requests.get(base_url, params=params, headers=headers)
        
        # 2. 인코딩 강제 설정 (핵심 부분)
        # 한경컨센서스는 실제 응답 헤더와 무관하게 콘텐츠가 euc-kr인 경우가 많습니다.
        resp.encoding = 'utf-8' 
        
        # 3. BeautifulSoup 객체 생성 시에도 인코딩 명시
        soup = BeautifulSoup(resp.content.decode('utf-8', 'replace'), 'html.parser')
        
        rows = soup.select("#contents > div.table_style01 > table > tbody > tr")
        
        results = []
        for row in rows:
            if "데이터가 없습니다" in row.get_text():
                break
                
            tds = row.select("td")
            if len(tds) < 6: continue

            # 데이터 파싱
            report_date = tds[0].get_text(strip=True)
            
            opinion = tds[3].get_text(strip=True)
            
            raw_price = tds[2].get_text(strip=True).replace(",", "")
            target_price = int(raw_price) if raw_price.isdigit() else 0
            
            firm = tds[5].get_text(strip=True)

            title_td = tds[1]
            title = (
                title_td.select_one("strong").get_text(strip=True)
                if title_td.select_one("strong")
                else title_td.get_text(strip=True)
            )

            pdf_link = None
            for a in title_td.select("a"):
                href = a.get("href", "")
                if href and any(kw in href.lower() for kw in [".pdf", "download", "file"]):
                    pdf_link = href if href.startswith("http") else "https://consensus.hankyung.com" + href
                    break

            if not pdf_link:
                first_a = title_td.select_one("a")
                if first_a:
                    href = first_a.get("href", "")
                    if href:
                        pdf_link = href if href.startswith("http") else "https://consensus.hankyung.com" + href


            results.append({
                "date": report_date,
                "firm": firm,
                "opinion": opinion,
                "target_price": target_price,
                "title": title, 
                "pdf_link":     pdf_link or "링크 없음"
            })

        if not results:
            print("❌ 검색 결과가 없습니다.")
            return

        print(f"✅ 총 {len(results)}건 수집 완료\n")
        # 출력 서식
        header = f"{'날짜':<12} | {'증권사':<12} | {'의견':<6} | {'적정가격':>10} | {'제목':<40} | 링크"
        print(header)
        print("-" * 100)
        
        for r in results:
            # 한글 정렬을 위해 f-string 포맷팅 조정
            print(f"{r['date']:<12} | {r['firm']:<10} | {r['opinion']:<6} | {r['target_price']:>10,}원 | {r['title']} | {r['pdf_link']}")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    get_hankyung_opinions("005930")