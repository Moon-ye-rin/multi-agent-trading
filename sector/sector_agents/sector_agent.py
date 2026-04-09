"""
섹터/종목 에이전트 (통합 오케스트레이터)
4개 수집 모듈을 순차 실행하고 결과를 하나의 페이로드로 조합합니다.
불/베어 에이전트에 전달할 정형 데이터를 생성합니다.
"""
import json
import sys, os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sector_collectors.supply_demand    import get_supply_demand_analysis
from sector_collectors.earnings         import get_earnings_analysis
from sector_collectors.naver_finance    import get_naver_finance_data
from sector_collectors.relative_strength import get_relative_strength_analysis
from sector_collectors.valuation        import get_valuation_analysis
from utils.logger                import get_logger

load_dotenv()
logger = get_logger("sector_agent")


def run_sector_agent(
    ticker: str,
    ticker_name: str,
    sector_etf: str,
) -> dict:
    """
    섹터/종목 에이전트 전체 실행

    Args:
        ticker:      종목 코드
        ticker_name: 종목명
        sector_etf:  섹터 ETF 코드

    Returns:
        dict: 불/베어 에이전트에 전달할 통합 페이로드
    """
    as_of = datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info(f"=== 섹터/종목 에이전트 시작: {ticker_name} ({ticker}) ===")

    payload: dict = {
        "meta": {
            "ticker":      ticker,
            "ticker_name": ticker_name,
            "sector_etf":  sector_etf,
            "as_of":       as_of,
        },
        "supply_demand":     None,
        "earnings":          None,
        "naver_finance":     None,
        "relative_strength": None,
        "valuation":         None,
        "errors":            [],
    }

    # ── 1. 수급 분석 ─────────────────────────────────────────────
    logger.info("[1/4] 수급 흐름 수집 중...")
    try:
        payload["supply_demand"] = get_supply_demand_analysis(ticker)
    except Exception as e:
        msg = f"수급 수집 오류: {e}"
        logger.error(msg)
        payload["errors"].append(msg)

    # ── 2. 실적 분석 ─────────────────────────────────────────────
    logger.info("[2/4] 실적 데이터 수집 중...")
    try:
        payload["earnings"] = get_earnings_analysis(ticker)
    except Exception as e:
        msg = f"실적 수집 오류: {e}"
        logger.error(msg)
        payload["errors"].append(msg)

    # ── 3. 네이버 증권 (목표주가·투자의견) ───────────────────────
    logger.info("[3/4] 네이버 증권 데이터 수집 중...")
    try:
        payload["naver_finance"] = get_naver_finance_data(ticker, ticker_name)
    except Exception as e:
        msg = f"네이버 증권 수집 오류: {e}"
        logger.error(msg)
        payload["errors"].append(msg)

    # ── 4. 섹터 상대강도 + 밸류에이션 ───────────────────────────
    logger.info("[4/4] 섹터 상대강도·밸류에이션 수집 중...")
    try:
        payload["relative_strength"] = get_relative_strength_analysis(ticker, sector_etf)
        payload["valuation"]         = get_valuation_analysis(ticker)
    except Exception as e:
        msg = f"상대강도/밸류에이션 수집 오류: {e}"
        logger.error(msg)
        payload["errors"].append(msg)

    logger.info(f"=== 섹터/종목 에이전트 완료 (오류: {len(payload['errors'])}건) ===")
    return payload


def save_payload(payload: dict, output_dir: str = "output") -> str:
    """결과를 JSON 파일로 저장"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ticker = payload["meta"]["ticker"]
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    path   = os.path.join(output_dir, f"sector_agent_{ticker}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"[저장] {path}")
    return path
