"""
섹터/종목 에이전트 실행 진입점
실행: python sector_main.py

수집된 데이터를 콘솔에 출력하여 수집 상태를 검증합니다.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# sector 디렉토리를 sys.path에 추가 (collectors, utils 등 하위 모듈 탐색용)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sector_agents.sector_agent import run_sector_agent, save_payload
from utils.logger import get_logger

logger = get_logger("main")

# ─────────────────────────────────────────────────────────────────
# 분석 대상 설정 (.env 우선, 없으면 기본값)
# ─────────────────────────────────────────────────────────────────
TICKER      = os.getenv("TARGET_TICKER",    "005930")
TICKER_NAME = os.getenv("TARGET_NAME",      "삼성전자")
SECTOR_ETF  = os.getenv("SECTOR_ETF_TICKER","091160")   # KODEX 반도체
OUTPUT_DIR  = os.getenv("OUTPUT_DIR",       "output")
SAVE_JSON   = os.getenv("SAVE_JSON",        "true").lower() == "true"


# ─────────────────────────────────────────────────────────────────
# 출력 헬퍼
# ─────────────────────────────────────────────────────────────────
SEP  = "=" * 62
SEP2 = "-" * 62

def h1(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def h2(title: str):
    print(f"\n{SEP2}")
    print(f"  ▸ {title}")
    print(SEP2)

def row(label: str, value, unit: str = ""):
    val_str = f"{value:,.1f}" if isinstance(value, float) else str(value)
    print(f"  {label:<30} {val_str} {unit}".rstrip())

def na(value) -> str:
    return str(value) if value is not None else "N/A"

def pct(value) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"

def bil(value) -> str:
    """억원 포맷"""
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}억"


# ─────────────────────────────────────────────────────────────────
# 섹션별 출력 함수
# ─────────────────────────────────────────────────────────────────

def print_meta(meta: dict):
    h1(f"섹터/종목 에이전트 수집 결과 — {meta['ticker_name']} ({meta['ticker']})")
    print(f"  수집 시각  : {meta['as_of']}")
    print(f"  섹터 ETF   : {meta['sector_etf']}")


def print_supply_demand(sd: dict):
    h2("1. 수급 흐름 (외국인 · 기관 · 개인)")
    if not sd or "error" in sd:
        print(f"  ⚠️  데이터 없음: {sd}")
        return

    headers = f"  {'':30} {'외국인':>12} {'기관':>12} {'개인':>12}"
    print(headers)
    print(f"  {'-'*66}")

    for period in ["20d", "60d", "120d"]:
        d = sd.get(period)
        if d:
            print(
                f"  {'누적 순매수 (' + period + ')':30}"
                f" {bil(d['foreign']):>12}"
                f" {bil(d['institutional']):>12}"
                f" {bil(d['individual']):>12}"
            )

    streak = sd.get("streak", {})
    print()
    print(f"  {'최근 5거래일 외국인 연속매수':30} {streak.get('foreign_consecutive_buy', 'N/A')}일")
    print(f"  {'최근 5거래일 외국인 연속매도':30} {streak.get('foreign_consecutive_sell', 'N/A')}일")
    print(f"  {'기관 5일 순매수':30} {bil(streak.get('institutional_5d_net'))}")
    print(f"  {'기관 5일 트렌드':30} {streak.get('institutional_5d_trend', 'N/A')}")
    print()
    print(f"  {'단기·중기 방향 일치':30} {'✅ 일치' if sd.get('trend_consistency') else '❌ 불일치'}")
    print(f"  {'매수/매도 강도 변화':30} {sd.get('intensity_change', 'N/A')}")


def print_earnings(ea: dict):
    h2("2. 실적 분석 (DART API)")
    if not ea or "error" in ea:
        print(f"  ⚠️  데이터 없음: {ea}")
        return

    note = ea.get("note", "")
    if note:
        print(f"  📌 {note}")

    print(f"\n  최근 분기  : {ea.get('latest_period', 'N/A')}")
    print(f"  corp_code  : {ea.get('corp_code', 'N/A')}")
    print()

    # 분기별 실적 테이블
    quarters = ea.get("quarters", {})
    print(f"  {'분기':<12} {'영업이익(억)':>14} {'매출액(억)':>14}")
    print(f"  {'-'*42}")
    for key in ["2025_3Q", "2025_2Q", "2025_1Q", "2024_3Q", "2024_ANN"]:
        q = quarters.get(key)
        if q:
            print(
                f"  {key:<12}"
                f" {q['op_income']:>13,.1f}"
                f" {q['revenue']:>13,.1f}"
            )
        else:
            print(f"  {key:<12} {'N/A':>14} {'N/A':>14}")

    print()
    yoy = ea.get("yoy", {})
    qoq = ea.get("qoq", {})
    print(f"  {'영업이익 YoY 변화':30} {pct(yoy.get('op_income_chg'))}")
    print(f"  {'매출 YoY 변화':30} {pct(yoy.get('revenue_chg'))}")
    print(f"  {'영업이익 QoQ 변화':30} {pct(qoq.get('op_income_chg'))}")
    print()
    print(f"  {'3분기 연속 실적 방향':30} {ea.get('trend_3q', 'N/A')}")


def print_naver_finance(nf: dict):
    h2("3. 네이버 증권 — 목표주가 · 투자의견")
    if not nf or "error" in nf:
        print(f"  ⚠️  데이터 없음: {nf}")
        return

    # 현재가
    cp = nf.get("current_price_info", {})
    print(f"\n  ▶ 현재 주가")
    print(f"  {'현재가':30} {na(cp.get('current_price'))}원")
    print(f"  {'전일 대비':30} {na(cp.get('change'))}원 ({na(cp.get('change_pct'))}%)")
    print(f"  {'시가총액':30} {na(cp.get('market_cap_100m'))}억원")

    # 애널리스트 의견
    ao = nf.get("analyst_opinions", {})
    if "error" not in ao:
        print(f"\n  ▶ 목표주가 (평균)")
        tp = ao.get("avg_target_price", {})
        current_price = cp.get("current_price")
        for period, label in [("all", "전체"), ("3m", "최근 3개월"), ("1m", "최근 1개월")]:
            val = tp.get(period)
            if val and current_price:
                gap = (val - current_price) / current_price * 100
                print(f"  {label + ' 평균 목표주가':30} {val:,.0f}원  (괴리율 {gap:+.1f}%)")
            else:
                print(f"  {label + ' 평균 목표주가':30} N/A")

        print(f"\n  ▶ 목표주가 추세         : {ao.get('target_price_trend', 'N/A')}")

        print(f"\n  ▶ Buy 비율")
        br = ao.get("buy_ratio", {})
        rc = ao.get("report_count", {})
        for period, label in [("all", "전체"), ("3m", "최근 3개월"), ("1m", "최근 1개월")]:
            ratio = br.get(period)
            count = rc.get(period, 0)
            ratio_str = f"{ratio:.1f}%" if ratio is not None else "N/A"
            print(f"  {label:30} {ratio_str}  (리포트 {count}건)")

        print(f"\n  ▶ 최근 리포트 (상위 5건)")
        print(f"  {'날짜':<12} {'증권사':<16} {'의견':<10} {'목표주가':>10}")
        print(f"  {'-'*52}")
        for r in ao.get("reports", [])[:5]:
            print(
                f"  {r.get('date',''):<12}"
                f" {r.get('firm',''):<16}"
                f" {r.get('opinion',''):<10}"
                f" {r.get('target_price', 0):>9,.0f}원"
            )

    # 시장 정보
    mi = nf.get("market_info", {})
    if mi and "error" not in mi:
        print(f"\n  ▶ 52주 주가 정보")
        print(f"  {'52주 최고':30} {na(mi.get('52w_high'))}원")
        print(f"  {'52주 최저':30} {na(mi.get('52w_low'))}원")
        print(f"  {'현재 위치 (52주 내)':30} {na(mi.get('52w_position_pct'))}%")
        print(f"  {'외국인 보유율':30} {na(mi.get('foreign_ownership_pct'))}%")


def print_relative_strength(rs: dict):
    h2("4. 섹터 상대강도")
    if not rs or "error" in rs:
        print(f"  ⚠️  데이터 없음: {rs}")
        return

    print(f"\n  섹터 ETF: {rs.get('sector_etf', 'N/A')}")
    print()
    print(f"  {'기간':<6} {'종목 수익률':>12} {'섹터 수익률':>12} {'KOSPI':>10} {'RS(섹터대비)':>14} {'RS(KOSPI대비)':>14}")
    print(f"  {'-'*72}")

    history = rs.get("rs_history", {})
    for period in ["1m", "3m", "6m", "1y"]:
        d = history.get(period, {})
        print(
            f"  {period:<6}"
            f" {pct(d.get('stock_ret')):>12}"
            f" {pct(d.get('sector_ret')):>12}"
            f" {pct(d.get('kospi_ret')):>10}"
            f" {pct(d.get('rs_vs_sector')):>14}"
            f" {pct(d.get('rs_vs_kospi')):>14}"
        )

    print()
    print(f"  {'상대강도 추세':30} {rs.get('rs_trend', 'N/A')}")
    print(f"  {'섹터 vs 종목 진단':30} {rs.get('sector_issue', 'N/A')}")
    print(f"  {'상대강도 최고 구간':30} {rs.get('strongest_period', 'N/A')}")


def print_valuation(va: dict):
    h2("5. 밸류에이션 (PER · PBR 역사적 밴드)")
    if not va or "error" in va:
        print(f"  ⚠️  데이터 없음: {va}")
        return

    current = va.get("current", {})
    print(f"\n  ▶ 현재 지표")
    print(f"  {'PER':30} {na(current.get('per'))}배")
    print(f"  {'PBR':30} {na(current.get('pbr'))}배")
    print(f"  {'EPS':30} {na(current.get('eps'))}원")
    print(f"  {'BPS':30} {na(current.get('bps'))}원")
    print(f"  {'배당수익률':30} {na(current.get('div_yield'))}%")

    per_b = va.get("per_band", {})
    pbr_b = va.get("pbr_band", {})

    if per_b:
        print(f"\n  ▶ PER 3년 역사적 밴드")
        print(f"  {'현재':30} {na(per_b.get('current'))}배")
        print(f"  {'3년 최소':30} {na(per_b.get('min_3y'))}배")
        print(f"  {'3년 최대':30} {na(per_b.get('max_3y'))}배")
        print(f"  {'3년 중앙값':30} {na(per_b.get('median_3y'))}배")
        print(f"  {'3년 내 백분위':30} {na(per_b.get('pct_3y'))}%")
        print(f"  {'판단':30} {va.get('per_label', 'N/A')}")

    if pbr_b:
        print(f"\n  ▶ PBR 3년 역사적 밴드")
        print(f"  {'현재':30} {na(pbr_b.get('current'))}배")
        print(f"  {'3년 최소':30} {na(pbr_b.get('min_3y'))}배")
        print(f"  {'3년 최대':30} {na(pbr_b.get('max_3y'))}배")
        print(f"  {'3년 중앙값':30} {na(pbr_b.get('median_3y'))}배")
        print(f"  {'3년 내 백분위':30} {na(pbr_b.get('pct_3y'))}%")
        print(f"  {'판단':30} {va.get('pbr_label', 'N/A')}")

    print()
    print(f"  {'EPS 트렌드':30} {va.get('eps_trend', 'N/A')}")
    print(f"  {'EPS YoY 변화':30} {pct(va.get('eps_yoy_chg'))}")

    note = va.get("note", "")
    if note:
        print(f"\n  📌 {note}")


def print_errors(errors: list):
    if errors:
        h2("⚠️  수집 오류 목록")
        for i, e in enumerate(errors, 1):
            print(f"  {i}. {e}")


def print_summary(payload: dict):
    """불/베어 에이전트 전달 요약"""
    h2("📦 불/베어 에이전트 전달 데이터 요약")
    modules = [
        ("supply_demand",     "수급 흐름"),
        ("earnings",          "실적 분석"),
        ("naver_finance",     "목표주가·투자의견"),
        ("relative_strength", "섹터 상대강도"),
        ("valuation",         "밸류에이션"),
    ]
    for key, label in modules:
        data = payload.get(key)
        status = "✅ 수집 완료" if data and "error" not in data else "❌ 수집 실패"
        print(f"  {label:<20} {status}")

    note_count = 1 if payload.get("earnings", {}).get("note", "").startswith("⚠️") else 0
    print()
    print(f"  → 총 {len(payload.get('errors', []))}건 오류 / 더미 데이터 {note_count}건")
    print(f"  → 판단(어닝 서프라이즈/쇼크 등)은 불/베어 에이전트에 위임")


# ─────────────────────────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────────────────────────
def main():
    # 1. 에이전트 실행
    payload = run_sector_agent(
        ticker=TICKER,
        ticker_name=TICKER_NAME,
        sector_etf=SECTOR_ETF,
    )

    # 2. 콘솔 출력
    print_meta(payload["meta"])
    print_supply_demand(payload.get("supply_demand"))
    print_earnings(payload.get("earnings"))
    print_naver_finance(payload.get("naver_finance"))
    print_relative_strength(payload.get("relative_strength"))
    print_valuation(payload.get("valuation"))
    print_errors(payload.get("errors", []))
    print_summary(payload)

    # 3. JSON 저장
    if SAVE_JSON:
        saved_path = save_payload(payload, OUTPUT_DIR)
        print(f"\n  💾 JSON 저장 완료: {saved_path}")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    main()
