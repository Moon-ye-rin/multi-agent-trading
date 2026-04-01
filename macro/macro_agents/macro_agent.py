import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from macro_collectors.ecos_api import get_macro_raw_data
from macro_collectors.quant_models import run_macro_quant_pipeline
from utils.logger import get_logger

load_dotenv()
logger = get_logger("macro_agent")

def run_macro_agent() -> dict:
    as_of = datetime.now().strftime("%Y-%m-%d %H:%M")
    logger.info("=== 매크로 에이전트 시작 ===")
    
    payload = {
        "meta": {
            "as_of": as_of,
            "base_models": ["3-State Markov Regime Switching", "PCA-based FSI"]
        },
        "raw_indicators": None,
        "quantitative_models": None,
        "objective_analysis": None,
        "errors": []
    }
    
    try:
        logger.info("[1/2] 원천 데이터 수집 모듈 가동")
        df_merged = get_macro_raw_data()
        
        logger.info("[2/2] 퀀트 모델 파이프라인 가동")
        model_result = run_macro_quant_pipeline(df_merged)
        
        payload["raw_indicators"] = model_result["level_1_raw_indicators"]
        payload["quantitative_models"] = model_result["level_2_quantitative_models"]
        payload["objective_analysis"] = model_result["level_3_objective_analysis"]
        
    except Exception as e:
        msg = f"에이전트 구동 중 오류 발생: {e}"
        logger.error(msg)
        payload["errors"].append(msg)

    logger.info(f"=== 매크로 에이전트 완료 (오류: {len(payload['errors'])}건) ===")
    return payload

def save_payload(payload: dict, output_dir: str = "output") -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"macro_agent_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return path