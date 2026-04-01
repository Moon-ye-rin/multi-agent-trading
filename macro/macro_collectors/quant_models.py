import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import statsmodels.api as sm
import warnings
from utils.logger import get_logger

warnings.filterwarnings("ignore")
logger = get_logger("quant_models")

def run_macro_quant_pipeline(df_merged: pd.DataFrame) -> dict:
    """전처리 -> PCA -> 마코프 모델 연산 -> JSON 보고서 생성 통합 파이프라인"""
    
    # 1. 전처리 및 스프레드 계산
    logger.info("  ▸ [Quant] 데이터 전처리 및 스프레드 계산...")
    df = df_merged.copy()
    df['KOSPI_Ret'] = df['KOSPI'].pct_change() * 100
    df['USD_KRW_Ret'] = df['USD_KRW'].pct_change() * 100
    df['Term_Spread'] = df['Bond_10Y'] - df['Bond_3Y']
    df['Credit_Spread'] = df['Corp_3Y'] - df['Bond_3Y']
    df['Term_Spread_Diff'] = df['Term_Spread'].diff()
    df['Credit_Spread_Diff'] = df['Credit_Spread'].diff()
    df.dropna(inplace=True)
    
    # 2. PCA 요인 추출
    logger.info("  ▸ [Quant] PCA 단일 거시 요인(FSI) 추출...")
    features = ['KOSPI_Ret', 'USD_KRW_Ret', 'Term_Spread_Diff', 'Credit_Spread_Diff']
    X_scaled = StandardScaler().fit_transform(df[features])
    pca = PCA(n_components=1)
    df['FSI_Factor'] = pca.fit_transform(X_scaled)
    logger.info(f"    - PCA 설명력: {pca.explained_variance_ratio_[0]*100:.2f}%")
    
    # 3. 마코프 국면전환 모형
    logger.info("  ▸ [Quant] 3-State 마코프 국면전환 모형 학습 중...")
    model = sm.tsa.MarkovRegression(df['FSI_Factor'], k_regimes=3, trend='c', switching_variance=True)
    result = model.fit(search_reps=20)
    df['Prob_State_0'] = result.smoothed_marginal_probabilities[0]
    df['Prob_State_1'] = result.smoothed_marginal_probabilities[1]
    df['Prob_State_2'] = result.smoothed_marginal_probabilities[2]
    
    # 4. JSON 포맷팅
    return generate_macro_report(df)

def generate_macro_report(df_final: pd.DataFrame) -> dict:
    latest = df_final.iloc[-1]
    prev_day = df_final.iloc[-2]
    prev_week = df_final.iloc[-6] if len(df_final) >= 6 else prev_day
    
    c_prob_0, c_prob_1, c_prob_2 = latest['Prob_State_0'], latest['Prob_State_1'], latest['Prob_State_2']
    dominant_prob = max(c_prob_0, c_prob_1, c_prob_2)
    
    if c_prob_2 >= 0.5:
        regime, risk = "위기/위험 (Crisis)", "High"
    elif c_prob_1 >= 0.5:
        regime, risk = "경계/둔화 (Caution)", "Medium"
    else:
        regime, risk = "정상/안정 (Normal)", "Low"
        
    return {
        "level_1_raw_indicators": {
            "market_index": {
                "KOSPI": {"current": round(latest['KOSPI'], 2), "dod_change_pct": round(latest['KOSPI_Ret'], 2)},
                "USD_KRW": {"current": round(latest['USD_KRW'], 2), "dod_change_pct": round(latest['USD_KRW_Ret'], 2)}
            },
            "interest_rates_spread": {
                "Term_Spread": {"current": round(latest['Term_Spread'], 3), "wow_change_pt": round(latest['Term_Spread'] - prev_week['Term_Spread'], 3)},
                "Credit_Spread": {"current": round(latest['Credit_Spread'], 3), "wow_change_pt": round(latest['Credit_Spread'] - prev_week['Credit_Spread'], 3)}
            }
        },
        "level_2_quantitative_models": {
            "fsi_factor_score": round(latest['FSI_Factor'], 4),
            "regime_probabilities": {
                "state_0_normal": round(c_prob_0, 4), "state_1_caution": round(c_prob_1, 4), "state_2_crisis": round(c_prob_2, 4)
            }
        },
        "level_3_objective_analysis": {
            "current_regime_diagnosis": f"현재 한국 경기 국면은 {regime} 상태이며, 해당 국면 진입 확률이 {round(dominant_prob*100, 1)}%로 지배적임.",
            "risk_assessment": f"투자 환경 위험도는 {risk} 수준. 장단기 금리차가 {round(latest['Term_Spread'], 3)}%p를 기록하고 있음.",
            "momentum": "요인 수치 상승" if latest['FSI_Factor'] > prev_day['FSI_Factor'] else "요인 수치 하락"
        }
    }