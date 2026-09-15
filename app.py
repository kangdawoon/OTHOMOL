# -*- coding: utf-8 -*-
"""
오쏘몰 SOV 대시보드 (Streamlit)

캠페인은 실제 미디어 집행 없이 진행되는 학습 프로젝트다. 채널별 유입·전환은
측정 불가능하며, 이 대시보드는 지금 실측 가능한 대체 지표(SOV·비교의도 검색지수)로
"오쏘몰이 40대의 고려상표군에 들어가고 있는가"라는 가설을 검증하기 위한 것이다.
실집행 데이터가 아니며, 아직 오지 않은 집행 기간은 실행한 것처럼 보여주지 않는다.
"""
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
import fetch_sov as fs

st.set_page_config(page_title="오쏘몰 SOV 대시보드", layout="wide")

# ---------------------------------------------------------------------------
# 공통 스타일 (v5 목업: 크림 배경 · 오렌지 포인트 · 네이비 인사이트 배너)
# 화면 구조·데이터 로직은 그대로 두고 스타일만 입히는 순수 CSS 주입.
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    html, body, .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stHeader"],
    .main .block-container {
        background-color: #FDFBF6 !important;
    }
    body, p, div, span, li { color: #1B1B18; }

    /* primaryColor(#E85D25)가 config.toml만으로 안 먹는 환경 대비 — 버튼도 직접 오렌지로 고정 */
    .stButton > button {
        background-color: #E85D25 !important;
        color: #FFFFFF !important;
        border: 1px solid #E85D25 !important;
    }
    .stButton > button:hover {
        background-color: #C94E1D !important;
        border-color: #C94E1D !important;
        color: #FFFFFF !important;
    }

    .odm-notice {
        background: #F1EFE8;
        border-radius: 10px;
        padding: 14px 18px;
        color: #1B1B18;
        font-size: 0.95em;
    }

    .odm-card {
        background: #FFFFFF;
        border: 0.5px solid #E7E5DC;
        border-radius: 12px;
        padding: 16px 20px;
    }
    .odm-card + .odm-card { margin-top: 12px; }

    .odm-badge {
        display: inline-block;
        background: #E85D25;
        color: #FFFFFF;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.55em;
        font-weight: 600;
        vertical-align: middle;
    }
    .odm-badge-green {
        display: inline-block;
        background: #1F7A45;
        color: #FFFFFF;
        padding: 2px 10px;
        border-radius: 10px;
        font-size: 0.75em;
        font-weight: 600;
    }

    .odm-banner {
        background: #1B2A44;
        color: #E3E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        font-size: 0.95em;
        line-height: 1.5;
    }

    .odm-kpi-label { font-size: 13px; color: #6B6A63; margin-bottom: 6px; }
    .odm-kpi-value {
        font-size: 28px; font-weight: 700; color: #1B1B18;
        word-break: keep-all; overflow-wrap: break-word;
    }
    .odm-kpi-value.odm-kpi-value-sm { font-size: 20px; }
    .odm-kpi-help { font-size: 12px; color: #9B9A90; margin-top: 6px; }

    .odm-milestone {
        border-radius: 12px;
        padding: 14px;
        background: #FFFFFF;
    }
    .odm-milestone-default { border: 1px solid #E7E5DC; }
    .odm-milestone-current { border: 3px solid #1F7A45; }

    .odm-status-table { width: 100%; border-collapse: collapse; }
    .odm-status-table th, .odm-status-table td {
        text-align: left;
        padding: 10px 12px;
        border-bottom: 1px solid #E7E5DC;
        font-size: 0.9em;
        vertical-align: top;
    }
    .odm-status-table th { color: #6B6A63; font-weight: 600; width: 22%; }
    .odm-status-table td { color: #1B1B18; }
    .odm-status-table tr:last-child th, .odm-status-table tr:last-child td { border-bottom: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

PHASE_ORDER = ["측정 체계 가동", "1차 리프트 확인", "누적 성과 검증"]
# 국면별 목표 수치는 전부 config.PHASE_TARGETS 한 곳에서만 관리한다.
# (여기에 숫자를 새로 하드코딩하지 않는다 — 수정 시 config.py만 고치면 된다.)


# ---------------------------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------------------------
def get_data():
    history = fs.load_history()
    if not history.empty:
        history = history.sort_values("period").reset_index(drop=True)
    meta = fs.load_meta()
    return history, meta


history_df, meta = get_data()
today = date.today()

# 진행 중인(아직 끝나지 않은) 주차는 화면에서 제외한다 — 데이터랩이 부분 집계 데이터를
# 돌려주기 때문에 그대로 쓰면 차트/타일 최신 지점이 다른 주차 대비 왜곡되어 보인다.
# 캐시 자체(cache/sov_history.json)에는 계속 저장되며, 그 주가 끝나면 자연히 완결된
# 데이터로 덮어써진다 (fetch_sov.load_history()는 원본을 그대로 반환).
if not history_df.empty:
    history_df = history_df[
        history_df["period"].apply(lambda p: fs.is_complete_week(p, today))
    ].reset_index(drop=True)

phase = fs.get_phase(today)
baseline, baseline_confirmed = fs.get_baseline(history_df)
is_pre_monitoring = phase == "캠페인 사전 모니터링"

# 캠페인 기간(12월~2월)은 팀이 임의로 정한 연습용 일정일 뿐이다. 이 대시보드의 목적은
# "실제로 측정·시각화되고 있다"는 것을 보여주는 것이므로, KPI 타일은 캠페인 기간 여부와
# 무관하게 지금 가진 데이터(완결 주차) 중 가장 최근 실측치를 항상 보여준다.
latest_row = None
if not history_df.empty:
    valid = history_df.dropna(subset=["SOV"])
    if not valid.empty:
        latest_row = valid.iloc[-1]


# ---------------------------------------------------------------------------
# 1. 헤더
# ---------------------------------------------------------------------------
header_left, header_right = st.columns([3, 1])
with header_left:
    st.markdown(
        "## 오쏘몰 SOV 대시보드&nbsp;&nbsp;"
        "<span class='odm-badge'>결국은, 오쏘몰</span>",
        unsafe_allow_html=True,
    )
with header_right:
    if meta.get("last_updated"):
        st.caption(f"API 자동 갱신 상태\n\n마지막 갱신: {meta['last_updated']}")
    else:
        st.caption("API 자동 갱신 상태\n\n아직 데이터를 수집하지 않았습니다.")
    if st.button("새로고침 (API 재호출)", use_container_width=True):
        with st.spinner("네이버 데이터랩 API 호출 중..."):
            try:
                history_df = fs.refresh()
                st.success("갱신 완료")
                st.rerun()
            except Exception as e:
                st.error(f"갱신 실패: {e}")

st.caption(
    "본 대시보드는 실제 미디어 집행 없이 진행되는 학습 프로젝트의 산출물입니다. "
    "채널별 유입·전환은 측정 불가하여, 실측 가능한 SOV·비교의도 검색지수로 가설을 검증합니다."
)
st.caption("진행 중인 이번 주 데이터는 집계 완료 후 반영됩니다.")
st.divider()


# ---------------------------------------------------------------------------
# 2. 타임라인 바
# ---------------------------------------------------------------------------
st.markdown("#### 캠페인 타임라인 (12월 ~ 2월, 1~12주차)")

if is_pre_monitoring:
    days_left = (config.CAMPAIGN_START - today).days
    st.markdown(
        f"<div class='odm-notice'>캠페인 시작 전 (D-{days_left}) · "
        f"캠페인 시작일: {config.CAMPAIGN_START.strftime('%Y-%m-%d')}</div>",
        unsafe_allow_html=True,
    )
else:
    week_num = min((today - config.CAMPAIGN_START).days // 7 + 1, 12)
    week_num = max(week_num, 1)
    segments = []
    for i in range(1, 13):
        month = "12월" if i <= 4 else ("1월" if i <= 8 else "2월")
        if i == week_num:
            segments.append(f"**[{i}주·{month}]**")
        else:
            segments.append(f"{i}")
    st.markdown(" — ".join(segments))
    st.progress(week_num / 12)


# ---------------------------------------------------------------------------
# 3. 인사이트 배너
# ---------------------------------------------------------------------------
# 상황별로 배경색이 바뀌던 기본 컴포넌트(info/success/warning) 대신, 항상 동일한 네이비
# 배너 안에서 내용 텍스트만 바뀌도록 통일한다.
if latest_row is None:
    banner_text = "아직 실측 데이터가 없습니다. '새로고침'으로 API를 호출해주세요."
else:
    phase_target = config.PHASE_TARGETS.get(phase, {})
    sov_target = phase_target.get("sov_target")
    target_label = phase_target.get("sov_target_label", "")
    baseline_note = "확정 베이스라인" if baseline_confirmed else "잠정 베이스라인(참고용 16.7%)"
    intent_val = latest_row.get("비교의도지수", "-")

    if is_pre_monitoring:
        # 캠페인 시작 전이라도 측정 자체는 계속되고 있음을 보여준다 — 목표 비교만 캠페인 기간에 적용.
        banner_text = (
            f"최근 실측 SOV {latest_row['SOV']}% · 비교의도 검색지수 {intent_val} — "
            f"캠페인 사전 모니터링 기간으로, 국면별 목표 비교는 12월 시작 후 적용됩니다 "
            f"({baseline_note} {baseline}% 기준)."
        )
    elif sov_target is None:
        banner_text = (
            f"[{phase}] 베이스라인 확인 단계입니다 (목표: 없음, 실측 자체가 목적). "
            f"최근 실측 SOV {latest_row['SOV']}% ({baseline_note} {baseline}% 기준). "
            f"비교의도 검색지수({intent_val})도 함께 확인하세요."
        )
    else:
        diff = round(latest_row["SOV"] - sov_target, 2)
        if diff >= 0:
            banner_text = (
                f"[{phase}] 최근 실측 SOV {latest_row['SOV']}% — 목표({sov_target}%, {target_label}) "
                f"대비 +{diff}%p 초과 달성. 비교의도 검색지수({intent_val})도 함께 확인하세요."
            )
        else:
            banner_text = (
                f"[{phase}] 최근 실측 SOV {latest_row['SOV']}% — 목표({sov_target}%, {target_label}) "
                f"대비 {diff}%p 미달. 1단계(브랜드 검색량)·2단계(비교의도 검색지수) 통합 추이를 먼저 점검하세요 "
                f"(개별 채널 귀속은 불가합니다)."
            )

st.markdown(f"<div class='odm-banner'>{banner_text}</div>", unsafe_allow_html=True)
st.divider()


# ---------------------------------------------------------------------------
# 4. KPI 타일
# ---------------------------------------------------------------------------
k1, k2, k3 = st.columns(3)
sov_display = f"{latest_row['SOV']}%" if latest_row is not None else "—"
intent_display = f"{latest_row['비교의도지수']}" if latest_row is not None else "—"


def kpi_card(col, label, value, help_text, small_value=False):
    value_class = "odm-kpi-value odm-kpi-value-sm" if small_value else "odm-kpi-value"
    col.markdown(
        f"<div class='odm-card'>"
        f"<div class='odm-kpi-label'>{label}</div>"
        f"<div class='{value_class}'>{value}</div>"
        f"<div class='odm-kpi-help'>{help_text}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


kpi_card(k1, "SOV (검색 점유율)", sov_display,
          f"베이스라인 {baseline}% ({'확정' if baseline_confirmed else '잠정'}) 대비")
kpi_card(k2, "비교의도 검색지수", intent_display,
          '"오쏘몰 비교"+"오쏘몰 후기"+"오쏘몰 가격" 검색지수 합 (대체 산출식)')
kpi_card(k3, "현재 국면", phase, "", small_value=True)

st.divider()


# ---------------------------------------------------------------------------
# 5. SOV·비교의도지수 추이 메인 차트 (최근 12주)
# ---------------------------------------------------------------------------
st.markdown("#### SOV · 비교의도 검색지수 추이 (최근 12주)")

if history_df.empty:
    st.info("아직 캐시된 데이터가 없습니다. '새로고침' 버튼으로 데이터를 수집해주세요.")
else:
    recent = history_df.tail(12).copy()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=recent["period"], y=recent["SOV"], name="SOV (%)",
        mode="lines+markers", connectgaps=True,
        line=dict(color="#E85D25", width=3), marker=dict(color="#E85D25"),
    ))
    fig.add_trace(go.Scatter(
        x=recent["period"], y=recent["비교의도지수"], name="비교의도 검색지수",
        mode="lines+markers", connectgaps=True,
        line=dict(color="#1B2A44", width=2, dash="dot"), marker=dict(color="#1B2A44"),
        yaxis="y2",
    ))

    # 국면 구분선 (12월|1월|2월) - 캠페인 기간이 차트 범위에 걸쳐 있을 때만 표시
    for boundary, label in [
        (config.CAMPAIGN_START, "12월 시작"),
        (config.DEC_END, "1월 시작"),
        (config.JAN_END, "2월 시작"),
    ]:
        b_str = boundary.strftime("%Y-%m-%d")
        if recent["period"].min() <= b_str <= recent["period"].max():
            fig.add_vline(x=b_str, line_width=1, line_dash="dash", line_color="gray",
                          annotation_text=label, annotation_position="top")

    # 국면별 목표 기준선 (절대 목표값). sov_target이 None인 국면(12월)은 기준선을 그리지 않는다.
    # 선 위에 텍스트(annotation_text)를 얹으면 우측에서 서로 겹치므로, 선만 그리고
    # 설명은 차트 아래 캡션으로 뺀다.
    for ph, target in config.PHASE_TARGETS.items():
        if target.get("sov_target") is None:
            continue
        fig.add_hline(y=target["sov_target"], line_width=1, line_dash="dot", line_color="#FFA94D")
    fig.add_hline(y=baseline, line_width=1, line_color="#999")

    # 목표선(예: 20%)이 실측 SOV 범위 밖에 있어도 잘리지 않도록 y축 범위에 포함시켜준다.
    sov_targets = [t["sov_target"] for t in config.PHASE_TARGETS.values() if t.get("sov_target") is not None]
    y_values = [baseline] + sov_targets + recent["SOV"].dropna().tolist()
    y_min = min(y_values) - 1
    y_max = max(y_values) + 1

    fig.update_layout(
        yaxis=dict(title="SOV (%)", range=[y_min, y_max]),
        yaxis2=dict(title="비교의도 검색지수", overlaying="y", side="right",
                     title_standoff=10, tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=40, b=20, r=80),
        height=420,
        plot_bgcolor="#FDFBF6",
        paper_bgcolor="#FDFBF6",
    )
    st.plotly_chart(fig, use_container_width=True)
    baseline_label = f"베이스라인 {baseline}%{'(확정)' if baseline_confirmed else '(잠정)'}"
    target_labels = " · ".join(
        f"{t['month']} 목표 {t['sov_target']}%"
        for t in config.PHASE_TARGETS.values() if t.get("sov_target") is not None
    )
    st.caption(f"점선: {baseline_label} · {target_labels}")
    st.caption("결측 주차는 선으로 이어서 표시했습니다 (실측치 없음을 의미하며 보간값이 아닙니다).")

st.divider()


# ---------------------------------------------------------------------------
# 6. 1·2단계 효과 미니차트 2열
# ---------------------------------------------------------------------------
st.markdown("#### 1·2단계 효과 (공통 대체지표)")
m1, m2 = st.columns(2)

with m1:
    st.markdown("**1단계 — 네이버광고 · 카카오비즈보드 · 네이버밴드**")
    st.caption("3채널 공통 대체지표(오쏘몰 브랜드 검색지수 자체 추이)이며, 개별 채널 귀속은 불가합니다.")
    if not history_df.empty:
        recent = history_df.tail(12)
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=recent["period"], y=recent[config.TARGET], mode="lines+markers",
                                   connectgaps=True,
                                   line=dict(color="#E85D25", width=2), marker=dict(color="#E85D25")))
        fig1.update_layout(height=260, margin=dict(t=10, b=10), yaxis_title="브랜드 검색지수",
                            plot_bgcolor="#FDFBF6", paper_bgcolor="#FDFBF6")
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.info("데이터 없음")

with m2:
    st.markdown("**2단계 — 네이버파워링크 · 블로그 · 유튜브**")
    st.caption("3채널 공통 대체지표(비교의도 검색지수 추이)이며, 개별 채널 귀속은 불가합니다.")
    if not history_df.empty:
        recent = history_df.tail(12)
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=recent["period"], y=recent["비교의도지수"], mode="lines+markers",
                                   connectgaps=True,
                                   line=dict(color="#1B2A44", width=2), marker=dict(color="#1B2A44")))
        fig2.update_layout(height=260, margin=dict(t=10, b=10), yaxis_title="비교의도 검색지수",
                            plot_bgcolor="#FDFBF6", paper_bgcolor="#FDFBF6")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("데이터 없음")

st.divider()


# ---------------------------------------------------------------------------
# 7. 월별 마일스톤 카드
# ---------------------------------------------------------------------------
st.markdown("#### 월별 마일스톤")
c1, c2, c3 = st.columns(3)
for col, ph_name in zip((c1, c2, c3), PHASE_ORDER):
    target = config.PHASE_TARGETS[ph_name]
    with col:
        is_current = phase == ph_name
        css_class = "odm-milestone-current" if is_current else "odm-milestone-default"
        st.markdown(
            f"<div class='odm-milestone {css_class}'>"
            f"<b>{target['month']}</b><br/>{ph_name}<br/>"
            f"<span style='font-size:0.85em;color:#6B6A63;'>{target['sov_target_label']}</span>"
            f"{'<br/><span class=\"odm-badge-green\">현재 국면</span>' if is_current else ''}"
            f"</div>",
            unsafe_allow_html=True,
        )

st.divider()


# ---------------------------------------------------------------------------
# 8. API 연동 상태 표
# ---------------------------------------------------------------------------
status_header_left, status_header_right = st.columns([4, 1])
with status_header_left:
    st.markdown("#### API 연동 상태")
with status_header_right:
    st.markdown(
        "<div style='text-align:right;padding-top:8px;'><span class='odm-badge-green'>연결됨</span></div>",
        unsafe_allow_html=True,
    )

status_rows = [
    ("데이터 소스", "네이버 데이터랩 검색어트렌드 API (openapi.naver.com/v1/datalab/search)"),
    ("SOV 산출 방식",
     "오쏘몰 / Σ(오쏘몰+경쟁사 5종) × 100. 그룹 조회 한도(5개)로 2회 호출 후 오쏘몰을 공통 앵커로 재보정·합산"),
    ("비교의도 검색지수 소스",
     '"오쏘몰 비교"+"오쏘몰 후기"+"오쏘몰 가격" 검색지수 합 (검색광고 API 미보유로 인한 대체 산출식, 실제 연관검색어 데이터 아님)'),
    ("국면 판별 방식", "오늘 날짜 기준 자동 판별 (12월=측정 체계 가동, 1월=1차 리프트 확인, 2월=누적 성과 검증, 그 외=사전/사후 모니터링)"),
    ("갱신 주기", "수동 새로고침 (버튼 클릭 시 API 재호출, 로컬 캐시에 주차별 누적 저장)"),
    ("마지막 갱신 시각", meta.get("last_updated") or "데이터 미수집"),
]
rows_html = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in status_rows)
st.markdown(
    f"<div class='odm-card'><table class='odm-status-table'>{rows_html}</table></div>",
    unsafe_allow_html=True,
)
