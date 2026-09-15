# -*- coding: utf-8 -*-
"""
오쏘몰 SOV 대시보드 - 공통 설정값

이 프로젝트는 실제 미디어 집행 없이 진행되는 학습 프로젝트다.
채널별 유입/전환은 측정 불가능하므로, 지금 실측 가능한 대체 지표
(SOV·비교의도 검색지수)로 "오쏘몰이 40대 고려상표군에 들어가고 있는가"를
검증하는 것이 목적이다.
"""
from datetime import date

# ---- 브랜드 정의 ----
TARGET = "오쏘몰"
COMPETITORS = ["아임비타", "센트룸", "고려은단", "마이핏V", "에너씨슬"]
ALL_BRANDS = [TARGET] + COMPETITORS

# 데이터랩 그룹 조회 한도(5개)에 맞춰 두 번의 호출로 분리.
# 오쏘몰을 두 호출에 공통 앵커로 넣어 두 번째 호출 값을 첫 번째 호출 척도로 재보정한다.
CALL1_BRANDS = [TARGET] + COMPETITORS[:4]   # 오쏘몰, 아임비타, 센트룸, 고려은단, 마이핏V (5개)
CALL2_BRANDS = [TARGET] + COMPETITORS[4:]   # 오쏘몰, 에너씨슬 (2개)

# ---- 비교의도 검색지수 ----
# 원래 설계였던 "오쏘몰 비교/vs 연관검색어 비중"은 검색광고 API(별도 인증)가 있어야
# 산출 가능해 지금 보유한 데이터랩 키만으로는 구현 불가. 아래 3개 문구의 검색지수 합으로 대체한다.
# 화면에는 반드시 "비교의도 검색지수"로 표기하고 "연관검색어 비중"이라는 표현은 쓰지 않는다.
COMPARISON_KEYWORDS = ["오쏘몰 비교", "오쏘몰 후기", "오쏘몰 가격"]

# ---- 베이스라인 ----
# 캠페인 시작(12월 1주차) 이전 실측치는 참고용으로만 쓰고 베이스라인 갱신에는 반영하지 않는다.
# 12월 1주차 실측값이 들어오면 그 시점에 베이스라인을 정식 확정한다 (get_baseline 참고).
BASELINE_DEFAULT = 16.7

# ---- 캠페인 일정 ----
CAMPAIGN_START = date(2026, 12, 1)   # 12월 1주차 시작
DEC_END = date(2027, 1, 1)
JAN_END = date(2027, 2, 1)
FEB_END = date(2027, 3, 1)

# 국면별 SOV 목표. 델타(+%p)가 아니라 KPI 슬라이드에서 확정된 절대 목표값을 기준으로 한다.
# sov_target이 None인 국면(12월)은 "목표 대비 초과/미달" 비교를 하지 않고,
# sov_target_label 문구로만 안내한다. app.py는 이 값만 참조하고 숫자를 새로 하드코딩하지 않는다.
PHASE_TARGETS = {
    "측정 체계 가동": {"month": "12월", "sov_target": None, "sov_target_label": "베이스라인 확인"},
    "1차 리프트 확인": {"month": "1월", "sov_target": 18.0, "sov_target_label": "18%대 진입"},
    "누적 성과 검증": {"month": "2월", "sov_target": 20.0, "sov_target_label": "20%대+ (베이스라인 대비 +3~4%p)"},
}

TIME_UNIT = "week"
LOOKBACK_WEEKS = 16   # 새로고침 시 조회할 과거 주차 수 (최근 12주 차트 + 여유분)

CACHE_DIR = "cache"
CACHE_FILE = "sov_history.json"
