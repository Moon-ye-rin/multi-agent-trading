# pykrx, yfinance 데이터 수집 로직
import yfinance as yf
from pykrx import stock
from datetime import datetime, timedelta
import pandas as pd

class MarketSentimentCollector:
    def __init__(self):
        self.kospi_ticker = "^KS11"

    def fetch_all_data(self):
        # 1. 날짜 설정 (최근 7일)
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")

        # 2. 외국인 수급 데이터 (pykrx)
        # KOSPI 시장 전체의 투자자별 순매수량 합계
        df_investor = stock.get_market_net_purchases_of_equities(start_date, end_date, "KOSPI")
        foreign_net_buy = int(df_investor['외국인'].sum()) if '외국인' in df_investor.columns else 0

        # 3. 코스피 지수 변화율 (yfinance)
        kospi_df = yf.download(self.kospi_ticker, period="7d", progress=False)
        if not kospi_df.empty:
            curr_kospi = kospi_df['Close'].iloc[-1].item()
            prev_kospi = kospi_df['Close'].iloc[0].item()
            kospi_change = (curr_kospi - prev_kospi) / prev_kospi
            # 변화율이 0보다 크면 '상승', 작거나 같으면 '하락'
            market_trend = "상승" if kospi_change > 0 else "하락"
        else:
            kospi_change = 0.0
            market_trend = "정체"

        # 4. VKOSPI (API 대기 중 -> 일단 더미 데이터 처리)
        vkospi_dummy = {"value": 20.0, "change_weekly": 0.0}

        return {
            "vkospi": vkospi_dummy,
            "foreign_net_buy": foreign_net_buy,
            "kospi_change_rate": kospi_change,
            "market_trend": market_trend
        }
    
# --- 테스트 섹션 ---
if __name__ == "__main__":
    print("🔍 데이터 수집을 시작합니다...")
    
    # 1. 클래스 생성
    collector = MarketSentimentCollector()
    
    try:
        # 2. 데이터 수집 실행
        result = collector.fetch_all_data()
        
        # 3. 결과 출력
        print("\n✅ 수집 성공!")
        print("-" * 30)
        print(f"🔹 VKOSPI: {result['vkospi']['value']} (변화: {result['vkospi']['change_weekly']})")
        print(f"🔹 외국인 순매수합: {result['foreign_net_buy']:,} 원")
        print(f"🔹 코스피 변화율: {result['kospi_change_rate']:.2%}")
        print(f"🔹 시장 트렌드: {result['market_trend']}")
        print("-" * 30)
        
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")