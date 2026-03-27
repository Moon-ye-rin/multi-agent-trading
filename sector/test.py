# test_supply_demand.py
# 실행: python test_supply_demand.py

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta

SEP  = "=" * 60
SEP2 = "-" * 60

def h1(t): print(f"\n{SEP}\n  {t}\n{SEP}")
def h2(t): print(f"\n{SEP2}\n  ▸ {t}\n{SEP2}")
def ok(t):  print(f"  ✅ {t}")
def fail(t): print(f"  ❌ {t}")
def info(t): print(f"  ℹ️  {t}")

# ──────────────────────────────────────────────
# 1. pykrx 로그인 세션 확인
# ──────────────────────────────────────────────
h1("STEP 1 — KRX 로그인 세션 확인")
try:
    from pykrx.website.comm.auth import build_krx_session
    session = build_krx_session()
    if session:
        ok("KRX 로그인 세션 생성 성공")
    else:
        fail("세션 생성 실패 (KRX_ID/KRX_PW 확인 필요)")
        sys.exit(1)
except ImportError:
    fail("auth.py 패치 미적용 — patch_pykrx.py를 먼저 실행하세요")
    sys.exit(1)

# ──────────────────────────────────────────────
# 2. get_market_trading_value_by_investor 원시 데이터 확인
# ──────────────────────────────────────────────
h1("STEP 2 — get_market_trading_value_by_investor 원시 데이터")
from pykrx import stock

TICKER = "005930"
today  = datetime.today().strftime("%Y%m%d")
d20    = (datetime.today() - timedelta(days=30)).strftime("%Y%m%d")

try:
    df_inv = stock.get_market_trading_value_by_investor(d20, today, TICKER)
    if df_inv is None or df_inv.empty:
        fail("데이터 없음 (빈 DataFrame)")
    else:
        ok(f"데이터 수신 성공 — shape: {df_inv.shape}")
        print(f"\n  [인덱스(투자자구분)]\n  {list(df_inv.index)}")
        print(f"\n  [컬럼]\n  {list(df_inv.columns)}")
        print(f"\n  [전체 데이터]\n{df_inv.to_string()}")
except Exception as e:
    fail(f"조회 실패: {e}")

# ──────────────────────────────────────────────
# 3. get_market_trading_value_by_date 원시 데이터 확인
# ──────────────────────────────────────────────
h1("STEP 3 — get_market_trading_value_by_date 원시 데이터 (일자별)")
try:
    df_date = stock.get_market_trading_value_by_date(d20, today, TICKER)
    if df_date is None or df_date.empty:
        fail("데이터 없음 (빈 DataFrame)")
    else:
        ok(f"데이터 수신 성공 — shape: {df_date.shape}")
        print(f"\n  [컬럼]\n  {list(df_date.columns)}")
        print(f"\n  [최근 5거래일]\n{df_date.tail(5).to_string()}")
except Exception as e:
    fail(f"조회 실패: {e}")

# ──────────────────────────────────────────────
# 4. supply_demand 모듈 전체 실행
# ──────────────────────────────────────────────
h1("STEP 4 — supply_demand 모듈 실행")
try:
    from sector_collectors.supply_demand import get_supply_demand_analysis
    result = get_supply_demand_analysis(TICKER)

    if "error" in result:
        fail(f"수급 분석 실패: {result['error']}")
    else:
        ok("수급 분석 완료")

        h2("기간별 누적 순매수 (억원)")
        for period in ["20d", "60d", "120d"]:
            d = result.get(period)
            if d:
                print(f"  {period}: 외국인 {d['foreign']:+,.1f}억 | 기관 {d['institutional']:+,.1f}억 | 개인 {d['individual']:+,.1f}억")
            else:
                info(f"{period}: 데이터 없음")

        h2("최근 5거래일 연속 매수/매도")
        s = result.get("streak", {})
        print(f"  외국인 연속매수일: {s.get('foreign_consecutive_buy')}일")
        print(f"  외국인 연속매도일: {s.get('foreign_consecutive_sell')}일")
        print(f"  기관 5일 순매수:   {s.get('institutional_5d_net')}억")
        print(f"  기관 5일 트렌드:   {s.get('institutional_5d_trend')}")

        h2("방향성 진단")
        print(f"  단기·중기 방향 일치: {'✅' if result.get('trend_consistency') else '❌'}")
        print(f"  매도/매수 강도:      {result.get('intensity_change')}")

except Exception as e:
    fail(f"모듈 실행 오류: {e}")
    import traceback
    traceback.print_exc()

# ──────────────────────────────────────────────
# 5. pykrx 기타 함수 동작 확인 (OHLCV, PER/PBR)
# ──────────────────────────────────────────────
h1("STEP 5 — pykrx 기타 함수 동작 확인")

h2("OHLCV (최근 5거래일)")
try:
    df_ohlcv = stock.get_market_ohlcv(d20, today, TICKER)
    if df_ohlcv is not None and not df_ohlcv.empty:
        ok(f"OHLCV 수신 성공 — {len(df_ohlcv)}행")
        print(df_ohlcv.tail(3).to_string())
    else:
        fail("OHLCV 데이터 없음")
except Exception as e:
    fail(f"OHLCV 조회 실패: {e}")

h2("PER / PBR (펀더멘털)")
try:
    df_fund = stock.get_market_fundamental(today, today, TICKER)
    if df_fund is not None and not df_fund.empty:
        ok("펀더멘털 수신 성공")
        print(df_fund.to_string())
    else:
        fail("펀더멘털 데이터 없음")
except Exception as e:
    fail(f"펀더멘털 조회 실패: {e}")

h2("섹터 ETF OHLCV (KODEX 반도체 091160)")
try:
    df_etf = stock.get_market_ohlcv(d20, today, "091160")
    if df_etf is not None and not df_etf.empty:
        ok(f"ETF OHLCV 수신 성공 — {len(df_etf)}행")
        print(df_etf.tail(3).to_string())
    else:
        fail("ETF 데이터 없음")
except Exception as e:
    fail(f"ETF 조회 실패: {e}")

print(f"\n{SEP}")
print("  테스트 완료")
print(SEP)


from pykrx import stock
from datetime import datetime, timedelta

def test_samsung_supply_units(ticker="005930"):
    """
    삼성전자(005930)를 대상으로 실제 pykrx 반환값의 단위를 체크합니다.
    """
    end_date = datetime.today().strftime("%Y%m%d")
    start_date = (datetime.today() - timedelta(days=20)).strftime("%Y%m%d")
    
    print(f"Checking Supply Data for {ticker} from {start_date} to {end_date}")
    print("-" * 60)

    try:
        # 1. 투자자별 합계 데이터 가져오기 (Raw)
        df = stock.get_market_trading_value_by_investor(start_date, end_date, ticker)
        
        if df is None or df.empty:
            print("❌ 데이터를 가져오지 못했습니다.")
            return

        # 외국인(Foreign) 데이터 추출
        raw_val = df.loc["외국인", "순매수"]
        
        print(f"[RAW DATA] 외국인 20일 누적 순매수: {raw_val:,.0f} 원")
        
        # 2. 단위 변환 로직 적용 (수정 제안 버전)
        def convert_to_100m(val):
            return round(val / 1e8, 1)

        converted_val = convert_to_100m(raw_val)
        
        print(f"[CONVERTED] 변환된 값: {converted_val} 억 원")
        print("-" * 60)
        
        # 3. 비정상 데이터 판단 기준 안내
        if abs(converted_val) > 100000: # 10조원 이상인 경우
            print("⚠️ 경고: 누적 수급이 10조원을 넘습니다. 종목명과 기간을 다시 확인하세요.")
        else:
            print("✅ 정상: 단위 변환이 적절해 보입니다.")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    test_samsung_supply_units()
