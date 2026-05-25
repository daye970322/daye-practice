"""
kt cloud Azure MSP · GPU · C-Plan 통합 대시보드
"""

from datetime import date, datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── 상수 ───────────────────────────────────────────────────────
MARGIN_RATE = 1.204
MARGIN_PCT = 20.4
KT_RED = "#E60012"
KT_LIGHT_RED = "#FF6B6B"
DONUT_COLORS = ["#E60012", "#FF4444", "#FF8888"]
GAUGE_GREEN = "#22c55e"
GAUGE_YELLOW = "#eab308"
KT_MAIN = "KT본체"
KT_CLOUD = "kt cloud"
SUBSIDIARIES = ["kt ds", KT_CLOUD, "kt sat", "kt is", "kt 스카이라이프"]
ALL_COMPANIES = [KT_MAIN] + SUBSIDIARIES

GPU_TYPES = [
    "Standard_NC96ads_H100_v5",
    "Standard_ND96isr_H100_v5",
    "Standard_ND96isr_H200_v5",
]

CONTRACT_EXPIRY = date(2026, 6, 30)
CAPT_TOTAL = 1_365_000_000_000  # 1조3650억
CREDIT_Y1, CREDIT_Y2, CREDIT_Y3 = 160, 120, 120  # 억원
CPLAN_Y1_TARGET, CPLAN_Y1_ACTUAL = 1309, 1150
CPLAN_Y2_TARGET = 1900
CPLAN_Y2_CUMULATIVE = 800  # 8개월 누적 (억)
CPLAN_Y2_MONTHS = [
    "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
    "2026-03", "2026-04", "2026-05", "2026-06", "2026-07",
    "2026-08", "2026-09",
]
CPLAN_CURRENT_MONTH = "2026-05"
CPLAN_MONTH_LABELS = [m.replace("-", ".") for m in CPLAN_Y2_MONTHS]

GPU_UNIT_PRICE_TABLE = pd.DataFrame({
    "GPU 모델": ["H100 (ND96isr)", "H200 (ND96isr)", "NC96ads H100"],
    "VM SKU": [
        "Standard_ND96isr_H100_v5",
        "Standard_ND96isr_H200_v5",
        "Standard_NC96ads_H100_v5",
    ],
    "월 단가 (목업)": ["약 3,500만원/월", "약 5,000만원/월", "약 1,200만원/월"],
})

TODAY = date(2026, 5, 25)

st.set_page_config(
    page_title="kt cloud Azure MSP 대시보드",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    .block-container {{ padding-top: 1rem; }}
    div[data-testid="stMetric"] {{
        background: #fafafa;
        border: 1px solid #eee;
        border-radius: 8px;
        padding: 10px 14px;
    }}
    .banner-expiry {{
        background: linear-gradient(90deg, #fff5f5 0%, #fff 100%);
        border: 1px solid #fecaca;
        border-left: 5px solid {KT_RED};
        padding: 14px 18px;
        border-radius: 8px;
        margin-bottom: 1rem;
        font-size: 1.05rem;
    }}
    .banner-expiry strong {{ color: {KT_RED}; }}
    .signal-green {{ color: #16a34a; font-weight: 700; }}
    .signal-yellow {{ color: #ca8a04; font-weight: 700; }}
    .signal-red {{ color: {KT_RED}; font-weight: 700; }}
    .hero-kpi-row {{
        display: flex; gap: 16px; margin-bottom: 12px;
    }}
    .hero-kpi-box {{
        flex: 1;
        background: linear-gradient(135deg, #fff5f5 0%, #fff 100%);
        border: 2px solid {KT_RED};
        border-radius: 12px;
        padding: 22px 20px;
        text-align: center;
    }}
    .hero-kpi-box .label {{
        font-size: 0.95rem; color: #555; margin-bottom: 8px;
    }}
    .hero-kpi-box .value {{
        font-size: 2.2rem; font-weight: 800; color: {KT_RED};
    }}
    .hero-kpi-box .sub {{ font-size: 0.85rem; color: #888; margin-top: 6px; }}
    .hero-flow {{
        background: #fafafa;
        border-left: 4px solid {KT_RED};
        padding: 12px 16px;
        border-radius: 6px;
        margin-bottom: 20px;
        font-size: 1rem;
    }}
    .insight-box {{
        background: #fff8f8;
        border: 1px solid #fecaca;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 16px;
        font-size: 1rem;
    }}
    .insight-box strong {{ color: {KT_RED}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def format_억(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}억"


def format_억원(value: float, digits: int = 1) -> str:
    return f"{value / 1e8:.{digits}f}억"


def billing(cost: float) -> float:
    return cost * MARGIN_RATE


def margin(cost: float) -> float:
    return cost * (MARGIN_RATE - 1)


def mom_pct(cur: float, prev: float) -> float | None:
    if prev == 0:
        return None
    return (cur - prev) / prev * 100


def ri_gauge_color(rate: float) -> str:
    if rate >= 90:
        return GAUGE_GREEN
    if rate >= 70:
        return GAUGE_YELLOW
    return KT_RED


def style_idle_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    return df.style.set_table_styles(
        [
            {
                "selector": "thead th",
                "props": [
                    ("background-color", KT_RED),
                    ("color", "white"),
                    ("font-weight", "bold"),
                ],
            }
        ]
    )


def signal_class(rate: float) -> tuple[str, str]:
    if rate >= 90:
        return "🟢 정상", "signal-green"
    if rate >= 70:
        return "🟡 주의", "signal-yellow"
    return "🔴 위험", "signal-red"


def build_cplan_pace_figure(cplan_full: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cplan_full["월라벨"],
        y=cplan_full["누적페이스"],
        name="목표 페이스",
        mode="lines",
        line=dict(color="#9ca3af", dash="dash", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=cplan_full["월라벨"],
        y=cplan_full["누적실적"],
        name="누적 실적",
        mode="lines+markers",
        line=dict(color=KT_RED, width=3),
        connectgaps=False,
    ))
    current_label = CPLAN_CURRENT_MONTH.replace("-", ".")
    fig.add_vline(
        x=current_label,
        line_width=2,
        line_dash="dot",
        line_color=KT_RED,
    )
    y_top = float(cplan_full["누적페이스"].max())
    fig.add_annotation(
        x=current_label,
        y=y_top,
        text="현재(2026.05)",
        showarrow=False,
        yanchor="bottom",
        font=dict(color=KT_RED, size=11),
    )
    fig.update_layout(
        height=380,
        xaxis_title="월",
        yaxis_title="누적 금액 (억원)",
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig


def cplan_pace_insight(cumulative: float, months_elapsed: int) -> str:
    avg_monthly = cumulative / months_elapsed
    projected = avg_monthly * 12
    pct = projected / CPLAN_Y2_TARGET * 100
    return (
        f"현재 페이스 유지시 연간 예상 소진: **{projected:.0f}억** "
        f"(목표 대비 **{pct:.1f}%**)"
    )


def build_gpu_company_table(
    gpu_data: pd.DataFrame, month: str, prev: str | None, companies: list[str]
) -> pd.DataFrame:
    rows = []
    for co in companies:
        cur = gpu_data[
            (gpu_data["그룹사"] == co) & (gpu_data["월"] == month)
        ]["GPU비용"].sum()
        prv = (
            gpu_data[
                (gpu_data["그룹사"] == co) & (gpu_data["월"] == prev)
            ]["GPU비용"].sum()
            if prev
            else 0
        )
        chg = mom_pct(cur, prv)
        rows.append({
            "그룹사": co,
            "당월GPU비용": format_억원(cur),
            "전월대비증감": f"{chg:+.1f}%" if chg is not None else "—",
            "_증감수치": chg if chg is not None else 0,
        })
    return pd.DataFrame(rows)


def style_gpu_company_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    show = df.drop(columns=["_증감수치"])

    def highlight(row):
        chg = df.at[row.name, "_증감수치"]
        if chg is not None and chg >= 30:
            return ["background-color:#fef9c3;font-weight:600"] * len(row)
        return [""] * len(row)

    return show.style.apply(highlight, axis=1)


def gpu_tab_insight(
    gpu_data: pd.DataFrame, month: str, prev: str | None, idle_savings: float
) -> str:
    cloud_chg = 0.0
    if prev:
        cur = gpu_data[
            (gpu_data["그룹사"] == KT_CLOUD) & (gpu_data["월"] == month)
        ]["GPU비용"].sum()
        prv = gpu_data[
            (gpu_data["그룹사"] == KT_CLOUD) & (gpu_data["월"] == prev)
        ]["GPU비용"].sum()
        cloud_chg = mom_pct(cur, prv) or 0.0
    return (
        f"이번달 주요 변동: **{KT_CLOUD}** GPU 사용 **{cloud_chg:+.1f}%** 증가, "
        f"유휴 리소스 절감 가능액 **{format_억원(idle_savings)}**"
    )


def month_list(n: int = 12) -> list[str]:
    base = datetime(2026, 5, 1)
    return [
        (pd.Timestamp(base) - pd.DateOffset(months=i)).strftime("%Y-%m")
        for i in range(n - 1, -1, -1)
    ]


@st.cache_data
def generate_data(seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    months = month_list(12)

    # 월별 Azure 원가 (원) — KT본체 ~120억, 그룹사 합 ~8억
    base = {
        KT_MAIN: 12_000_000_000,
        "kt ds": 250_000_000,
        KT_CLOUD: 280_000_000,
        "kt sat": 100_000_000,
        "kt is": 180_000_000,
        "kt 스카이라이프": 90_000_000,
    }
    usage = []
    for m in months:
        f = 1 + rng.uniform(-0.03, 0.05)
        for co, b in base.items():
            spike = 1.38 if co == KT_CLOUD and m == months[-1] else 1.0
            usage.append({
                "월": m,
                "그룹사": co,
                "Azure원가": b * f * rng.uniform(0.94, 1.06) * spike,
            })
    usage_df = pd.DataFrame(usage)

    # GPU 비용 — KT본체 75%+
    gpu_rows = []
    for m in months[-3:]:
        total_gpu = rng.uniform(118, 128) * 1e8
        main_share = rng.uniform(0.76, 0.82)
        main_cost = total_gpu * main_share
        sub_total = total_gpu - main_cost
        sub_weights = rng.random(len(SUBSIDIARIES))
        sub_weights /= sub_weights.sum()
        for co in ALL_COMPANIES:
            if co == KT_MAIN:
                cost = main_cost
            else:
                cost = sub_total * sub_weights[SUBSIDIARIES.index(co)]
            for gtype in GPU_TYPES:
                share = rng.uniform(0.2, 0.45)
                gcost = cost * share / len(GPU_TYPES) * rng.uniform(0.8, 1.2)
                total_vm = max(2, int(gcost / 8e7))
                used_vm = max(1, int(total_vm * rng.uniform(0.5, 0.92)))
                gpu_rows.append({
                    "월": m,
                    "그룹사": co,
                    "GPU_VM종류": gtype,
                    "GPU비용": gcost,
                    "할당VM": total_vm,
                    "사용VM": used_vm,
                    "유휴VM": total_vm - used_vm,
                    "시간당단가": rng.choice([28_000, 32_000, 41_000]),
                })
    gpu_df = pd.DataFrame(gpu_rows)

    # 예약 인스턴스
    ri_rows = []
    for co in ALL_COMPANIES:
        for gtype in GPU_TYPES:
            contracted = rng.integers(6, 40) if co == KT_MAIN else rng.integers(0, 10)
            if contracted == 0:
                continue
            actual = max(1, int(contracted * rng.uniform(0.58, 0.98)))
            ri_rows.append({
                "그룹사": co,
                "GPU_VM종류": gtype,
                "계약수량": int(contracted),
                "실사용수량": int(actual),
            })
    ri_df = pd.DataFrame(ri_rows)

    # C-Plan 2년차 월별 (억) — 8개월 실적 + 12개월 페이스
    monthly_burn = [95, 102, 98, 105, 99, 101, 100, 100]  # 합 800억
    pace_monthly = CPLAN_Y2_TARGET / 12
    cumulative_actual = list(np.cumsum(monthly_burn))
    actual_full = cumulative_actual + [None] * (12 - len(cumulative_actual))
    cplan_y2_full = pd.DataFrame({
        "월": CPLAN_Y2_MONTHS,
        "월라벨": CPLAN_MONTH_LABELS,
        "누적페이스": [pace_monthly * (i + 1) for i in range(12)],
        "누적실적": actual_full,
    })
    cplan_y2 = cplan_y2_full[cplan_y2_full["월"] <= CPLAN_CURRENT_MONTH].dropna(
        subset=["누적실적"]
    )

    # 크레딧 월별 소진 (2년차, 억)
    credit_burn = pd.DataFrame({
        "월": CPLAN_Y2_MONTHS[:8],
        "소진액": [12, 11, 10, 9, 10, 9, 8, 6],
    })
    credit_y2_used = 75  # 억, 120억 중
    credit_y2_remain = CREDIT_Y2 - credit_y2_used

    budget_rows = []
    for company in ALL_COMPANIES:
        annual = usage_df[usage_df["그룹사"] == company]["Azure원가"].mean() * 12
        factor = 0.52 if company == KT_CLOUD else rng.uniform(0.92, 1.02)
        budget_rows.append({
            "그룹사": company,
            "항목": "Azure 인프라",
            "연간예산": annual * factor,
        })
    budget_df = pd.DataFrame(budget_rows)

    return {
        "usage": usage_df,
        "gpu": gpu_df,
        "ri": ri_df,
        "cplan_y2": cplan_y2,
        "cplan_y2_full": cplan_y2_full,
        "credit_burn": credit_burn,
        "credit_y2_remain": credit_y2_remain,
        "credit_y2_used": credit_y2_used,
        "budget": budget_df,
        "months": months,
    }


def build_company_table(companies: list[str], month: str, prev: str | None) -> pd.DataFrame:
    rows = []
    for co in companies:
        cur = usage_df[
            (usage_df["그룹사"] == co) & (usage_df["월"] == month)
        ]["Azure원가"].sum()
        prv = (
            usage_df[
                (usage_df["그룹사"] == co) & (usage_df["월"] == prev)
            ]["Azure원가"].sum()
            if prev
            else 0
        )
        chg = mom_pct(cur, prv)
        rows.append({
            "그룹사명": co,
            "당월원가": format_억원(cur),
            "청구액": format_억원(billing(cur)),
            "마진": format_억원(margin(cur)),
            "전월대비증감": f"{chg:+.1f}%" if chg is not None else "—",
            "_증감수치": chg if chg is not None else 0,
        })
    return pd.DataFrame(rows)


def style_company_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    show = df.drop(columns=["_증감수치"])

    def highlight(row):
        chg = df.at[row.name, "_증감수치"]
        if chg >= 30:
            css = f"background-color:#ffe4e4;color:{KT_RED};font-weight:600"
            return [css] * len(row)
        return [""] * len(row)

    return show.style.apply(highlight, axis=1)


def get_spike_companies(month: str, prev: str | None) -> list[dict]:
    if not prev:
        return []
    spikes = []
    for company in ALL_COMPANIES:
        cur = usage_df[
            (usage_df["그룹사"] == company) & (usage_df["월"] == month)
        ]["Azure원가"].sum()
        prv = usage_df[
            (usage_df["그룹사"] == company) & (usage_df["월"] == prev)
        ]["Azure원가"].sum()
        chg = mom_pct(cur, prv)
        if chg is not None and chg >= 30:
            spikes.append({
                "그룹사": company,
                "당월원가": format_억원(cur),
                "증감률": f"{chg:+.1f}%",
            })
    return spikes


def get_budget_alerts(
    budget_df: pd.DataFrame, companies: list[str], month_idx: int, month_list: list[str]
) -> pd.DataFrame:
    ytd_months = month_list[: month_idx + 1]
    alerts = []
    for company in companies:
        b = budget_df[
            (budget_df["그룹사"] == company)
            & (budget_df["항목"] == "Azure 인프라")
        ]["연간예산"].sum()
        used = usage_df[
            (usage_df["월"].isin(ytd_months)) & (usage_df["그룹사"] == company)
        ]["Azure원가"].sum()
        if b > 0:
            pct = used / b * 100
            if pct > 80:
                alerts.append({
                    "그룹사": company,
                    "항목": "Azure 인프라",
                    "예산사용률": pct,
                    "누적사용": format_억원(used),
                    "연간예산": format_억원(b),
                })
    return pd.DataFrame(alerts)


def style_budget_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    def highlight(row):
        css = f"background-color:#ffe4e4;color:{KT_RED};font-weight:600"
        return [css] * len(row)

    return df.style.apply(highlight, axis=1).format({"예산사용률": "{:.1f}%"})


# ── 데이터 ─────────────────────────────────────────────────────
data = generate_data()
usage_df = data["usage"]
gpu_df = data["gpu"]
ri_df = data["ri"]
cplan_y2 = data["cplan_y2"]
cplan_y2_full = data["cplan_y2_full"]
credit_burn = data["credit_burn"]
budget_df = data["budget"]
months = data["months"]

# ── 사이드바 ───────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 필터")
    sel_companies = st.multiselect("그룹사", ALL_COMPANIES, default=ALL_COMPANIES)
    sel_month = st.selectbox("월", months, index=len(months) - 1)
    st.divider()
    st.markdown("**계약 구조**")
    st.caption("CAPT 2024.09~2029.09 · 1조3,650억")
    st.caption(f"MSP 마진 {MARGIN_PCT}% · GPU 핵심 매출")
    st.caption("내부거래 2026.01~06 · 12월 연장 협의")

if not sel_companies:
    st.warning("그룹사를 하나 이상 선택해 주세요.")
    st.stop()

mi = months.index(sel_month)
prev_month = months[mi - 1] if mi > 0 else None

cur_u = usage_df[
    (usage_df["월"] == sel_month) & (usage_df["그룹사"].isin(sel_companies))
]
prev_u = (
    usage_df[
        (usage_df["월"] == prev_month) & (usage_df["그룹사"].isin(sel_companies))
    ]
    if prev_month
    else pd.DataFrame()
)

cur_cost = cur_u["Azure원가"].sum()
prev_cost = prev_u["Azure원가"].sum() if not prev_u.empty else 0
cur_bill = billing(cur_cost)
cur_margin = margin(cur_cost)
mom = mom_pct(cur_cost, prev_cost)

# GPU 당월
gpu_month = gpu_df[
    (gpu_df["월"] == sel_month) & (gpu_df["그룹사"].isin(sel_companies))
]

# C-Plan 달성률 (2년차 8개월 기준)
cplan_pace_8m = CPLAN_Y2_TARGET / 12 * 8
cplan_rate = CPLAN_Y2_CUMULATIVE / cplan_pace_8m * 100
cplan_signal, cplan_cls = signal_class(cplan_rate)

# 크레딧 잔액 (억) — 2년차 잔여 + 3년차 미수령
credit_balance_억 = data["credit_y2_remain"] + CREDIT_Y3

# 계약 잔여
days_left = (CONTRACT_EXPIRY - TODAY).days

# ══════════════════════════════════════════════════════════════
# 상단 알림 배너
# ══════════════════════════════════════════════════════════════
st.markdown(
    f'<div class="banner-expiry">'
    f"⚠️ <strong>내부거래 계약 만료 D-{max(days_left, 0)}</strong> "
    f"(만료일 2026.06.30) · 2026.12까지 연장 협의 진행 중"
    f"</div>",
    unsafe_allow_html=True,
)

st.title("☁️ kt cloud Azure MSP · GPU 통합 대시보드")
st.caption(
    f"kt cloud ↔ MS CAPT(5년) · kt cloud ↔ KT그룹사 연간 내부거래 · "
    f"{sel_month} 기준 · GPU 중심 매출 구조"
)

y1_rate = CPLAN_Y1_ACTUAL / CPLAN_Y1_TARGET * 100
y2_rate = CPLAN_Y2_CUMULATIVE / (CPLAN_Y2_TARGET / 12 * 8) * 100

tab_overview, tab_gpu, tab_credit, tab_company, tab_alert = st.tabs([
    "📊 사업 개요",
    "🖥️ GPU 현황",
    "💳 크레딧 관리",
    "🏢 그룹사별 현황",
    "🚨 이상징후",
])

# ── 탭1: 사업 개요 ────────────────────────────────────────────
with tab_overview:
    st.markdown(
        f"""
        <div class="hero-kpi-row">
            <div class="hero-kpi-box">
                <div class="label">① 이번달 MS 지급액 (원가)</div>
                <div class="value">{format_억원(cur_cost)}</div>
                <div class="sub">kt cloud → Microsoft</div>
            </div>
            <div class="hero-kpi-box">
                <div class="label">② 이번달 그룹사 청구액 (×{MARGIN_RATE})</div>
                <div class="value">{format_억원(cur_bill)}</div>
                <div class="sub">원가 × {MARGIN_PCT}% 마진</div>
            </div>
            <div class="hero-kpi-box">
                <div class="label">③ 이번달 순마진</div>
                <div class="value">{format_억원(cur_margin)}</div>
                <div class="sub">청구액 − MS 지급액</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="hero-flow">kt cloud가 MS에 <strong>{format_억원(cur_cost)}</strong> 지불 '
        f"→ 그룹사에 <strong>{format_억원(cur_bill)}</strong> 청구 "
        f"→ <strong>{format_억원(cur_margin)}</strong> 마진</div>",
        unsafe_allow_html=True,
    )

    st.markdown("##### 세부 KPI")
    k = st.columns(6)
    k[0].metric("당월 청구액", format_억원(cur_bill))
    k[1].metric("당월 마진", format_억원(cur_margin))
    if mom is not None and prev_month:
        k[2].metric("전월 대비 증감률", f"{mom:+.1f}%")
    else:
        k[2].metric("전월 대비 증감률", "—")
    k[3].metric(
        "C-Plan 달성률",
        f"{cplan_rate:.1f}%",
        help=f"2년차 8개월 누적 {CPLAN_Y2_CUMULATIVE}억 / 페이스 {cplan_pace_8m:.0f}억",
    )
    k[4].metric("크레딧 잔액", format_억(credit_balance_억, 0))
    k[5].metric("계약 잔여기간", f"D-{max(days_left, 0)}", help="내부거래 2026.06.30 만료")

    st.markdown("##### 계약 현황")
    ct1, ct2, ct3, ct4 = st.columns(4)
    ct1.metric("CAPT (kt cloud↔MS)", format_억(CAPT_TOTAL / 1e8, 0), "2024.09 ~ 2029.09")
    ct2.metric("내부거래 계약", "2026.01 ~ 06", f"만료 D-{max(days_left, 0)}")
    ct3.metric("연장 협의", "2026.12", "진행 중")
    ct4.metric("MSP 마진", f"{MARGIN_PCT}%", f"청구 = 원가 × {MARGIN_RATE}")

    contract_tbl = pd.DataFrame({
        "계약": ["CAPT", "내부거래", "크레딧(3년)", "C-Plan 2년차"],
        "상대/범위": ["Microsoft", "KT그룹사", "MACC 400억", "25.10~26.09"],
        "금액·기간": [
            "1조3,650억 / 5년",
            "연간 · 2026.06 만료",
            "160+120+120억",
            f"목표 {CPLAN_Y2_TARGET}억",
        ],
        "상태": ["유효", "만료 임박", "2년차 진행", cplan_signal],
    })
    st.dataframe(contract_tbl, use_container_width=True, hide_index=True)

    st.markdown("##### C-Plan 달성률")
    st.markdown(
        f'<p>2년차 신호등: <span class="{cplan_cls}">{cplan_signal}</span> · '
        f"누적 {CPLAN_Y2_CUMULATIVE}억 / 8개월 페이스 {cplan_pace_8m:.0f}억 "
        f"({cplan_rate:.1f}%)</p>",
        unsafe_allow_html=True,
    )
    st.markdown("##### 연도별 목표 vs 실적")
    cplan_annual = pd.DataFrame({
        "연차": ["1년차\n(24.10~25.09)", "2년차\n(25.10~26.09)\n8개월"],
        "목표": [CPLAN_Y1_TARGET, CPLAN_Y2_TARGET / 12 * 8],
        "실적": [CPLAN_Y1_ACTUAL, CPLAN_Y2_CUMULATIVE],
    })
    fig_cplan = go.Figure()
    fig_cplan.add_trace(go.Bar(
        name="목표", x=cplan_annual["연차"], y=cplan_annual["목표"],
        marker_color="#d1d5db",
    ))
    fig_cplan.add_trace(go.Bar(
        name="실적", x=cplan_annual["연차"], y=cplan_annual["실적"],
        marker_color=KT_RED,
        text=cplan_annual["실적"].apply(lambda v: f"{v:.0f}억"),
        textposition="outside",
    ))
    fig_cplan.update_layout(
        barmode="group", height=320, yaxis_title="억원",
        legend=dict(orientation="h", y=1.12),
    )
    st.plotly_chart(fig_cplan, use_container_width=True)
    s1, s1c = signal_class(y1_rate)
    s2, s2c = signal_class(y2_rate)
    st.markdown(
        f"1년차 {y1_rate:.1f}% <span class='{s1c}'>{s1}</span> · "
        f"2년차(8M) {y2_rate:.1f}% <span class='{s2c}'>{s2}</span>",
        unsafe_allow_html=True,
    )

    st.markdown("##### C-Plan 2년차 페이스 (2025.10 ~ 2026.09)")
    st.plotly_chart(build_cplan_pace_figure(cplan_y2_full), use_container_width=True)
    months_elapsed = len(cplan_y2)
    st.markdown(cplan_pace_insight(CPLAN_Y2_CUMULATIVE, months_elapsed))

# ── 탭2: GPU 현황 ─────────────────────────────────────────────
with tab_gpu:
    idle_savings_total = 0.0
    if not gpu_month.empty:
        idle_tmp = gpu_month[gpu_month["유휴VM"] > 0].copy()
        if not idle_tmp.empty:
            idle_savings_total = (
                idle_tmp["유휴VM"] * idle_tmp["시간당단가"] * 730
            ).sum()

    st.markdown(
        f'<div class="insight-box">{gpu_tab_insight(gpu_df, sel_month, prev_month, idle_savings_total)}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("##### GPU 모델별 월 단가 (목업)")
    st.dataframe(GPU_UNIT_PRICE_TABLE, use_container_width=True, hide_index=True)

    if gpu_month.empty:
        st.info("선택한 조건의 GPU 데이터가 없습니다.")
    else:
        g_bar, g_pie = st.columns([1.4, 1])

        with g_bar:
            st.markdown("##### 그룹사별 GPU 사용 비용")
            by_co = (
                gpu_month.groupby("그룹사", as_index=False)["GPU비용"]
                .sum()
                .sort_values("GPU비용", ascending=True)
            )
            by_co["구분"] = by_co["그룹사"].apply(
                lambda x: "KT본체" if x == KT_MAIN else "그룹사"
            )
            fig_co = px.bar(
                by_co,
                x="GPU비용",
                y="그룹사",
                orientation="h",
                text=by_co["GPU비용"].apply(format_억원),
                color="구분",
                color_discrete_map={"KT본체": KT_RED, "그룹사": KT_LIGHT_RED},
            )
            fig_co.update_traces(textposition="outside")
            fig_co.update_layout(
                height=380,
                showlegend=True,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis_tickformat=".2s",
            )
            st.plotly_chart(fig_co, use_container_width=True)
            main_gpu = by_co[by_co["그룹사"] == KT_MAIN]["GPU비용"].sum()
            total_gpu = by_co["GPU비용"].sum()
            if total_gpu > 0:
                st.caption(
                    f"KT본체 GPU 비중: **{main_gpu / total_gpu * 100:.1f}%** "
                    f"(목표 75% 이상)"
                )

            st.markdown("##### 그룹사별 GPU 사용량 · 전월 대비")
            gpu_co_tbl = build_gpu_company_table(
                gpu_df, sel_month, prev_month, list(by_co["그룹사"])
            )
            st.dataframe(
                style_gpu_company_table(gpu_co_tbl),
                use_container_width=True,
                hide_index=True,
            )

        with g_pie:
            st.markdown("##### GPU VM 종류별 비용 분포")
            by_vm = gpu_month.groupby("GPU_VM종류", as_index=False)["GPU비용"].sum()
            vm_color_map = {vm: DONUT_COLORS[i] for i, vm in enumerate(GPU_TYPES)}
            fig_pie = px.pie(
                by_vm,
                values="GPU비용",
                names="GPU_VM종류",
                hole=0.35,
                color="GPU_VM종류",
                color_discrete_map=vm_color_map,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("##### 예약 인스턴스 · 실사용률")
        ri_show = ri_df[ri_df["그룹사"].isin(sel_companies)].copy()
        if not ri_show.empty:
            ri_show["실사용률"] = (
                ri_show["실사용수량"] / ri_show["계약수량"] * 100
            ).round(1)
            gauge_cols = st.columns(min(len(ri_show), 4))
            for i, row in enumerate(ri_show.head(4).itertuples()):
                with gauge_cols[i % len(gauge_cols)]:
                    fig_g = go.Figure(
                        go.Indicator(
                            mode="gauge+number",
                            value=row.실사용률,
                            title={
                                "text": f"{row.그룹사}<br><span style='font-size:0.7em'>"
                                f"{row.GPU_VM종류[:20]}…</span>"
                            },
                            number={"suffix": "%"},
                            gauge={
                                "axis": {"range": [0, 100]},
                                "bar": {"color": ri_gauge_color(row.실사용률)},
                                "bgcolor": "white",
                                "steps": [
                                    {"range": [0, 70], "color": "#f5f5f5"},
                                    {"range": [70, 90], "color": "#f5f5f5"},
                                    {"range": [90, 100], "color": "#f5f5f5"},
                                ],
                            },
                        )
                    )
                    fig_g.update_layout(
                        height=220, margin=dict(l=20, r=20, t=50, b=10)
                    )
                    st.plotly_chart(fig_g, use_container_width=True)
        else:
            st.info("예약 인스턴스 데이터 없음")

        st.markdown("##### 유휴 GPU 리소스 (절감 가능)")
        idle = gpu_month[gpu_month["유휴VM"] > 0].copy()
        if not idle.empty:
            idle["월절감가능액"] = idle["유휴VM"] * idle["시간당단가"] * 730
            idle_tbl = (
                idle.groupby(["그룹사", "GPU_VM종류"], as_index=False)
                .agg(유휴VM=("유휴VM", "sum"), 절감가능금액=("월절감가능액", "sum"))
                .sort_values("절감가능금액", ascending=False)
            )
            idle_tbl["절감가능금액"] = idle_tbl["절감가능금액"].apply(format_억원)
            idle_display = idle_tbl.rename(columns={"절감가능금액": "월 절감 가능액"})
            st.dataframe(
                style_idle_table(idle_display),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.success("유휴 GPU 리소스 없음")

# ── 탭3: 크레딧 관리 ──────────────────────────────────────────
with tab_credit:
    st.markdown("##### MACC 크레딧 현황")
    cr1, cr2, cr3 = st.columns(3)
    cr1.metric("1년차 (160억)", "소진 완료", delta="100%")
    cr2.metric(
        "2년차 (120억)",
        "진행 중",
        delta=f"잔여 {format_억(data['credit_y2_remain'], 0)}",
    )
    cr3.metric("3년차 (120억)", "미수령", delta="0%")

    st.progress(
        data["credit_y2_used"] / CREDIT_Y2,
        text=f"2년차 소진 {data['credit_y2_used']}억 / {CREDIT_Y2}억 "
        f"(잔여 {format_억(data['credit_y2_remain'], 0)})",
    )

    credit_status = pd.DataFrame({
        "연차": ["1년차", "2년차", "3년차"],
        "금액(억)": [CREDIT_Y1, CREDIT_Y2, CREDIT_Y3],
        "상태": ["완료", "진행중", "미수령"],
        "비고": [
            "160억 소진 완료",
            f"{data['credit_y2_used']}억 소진 · 잔여 {data['credit_y2_remain']}억",
            "120억 미수령",
        ],
    })
    st.dataframe(credit_status, use_container_width=True, hide_index=True)

    fig_credit = px.bar(
        credit_burn, x="월", y="소진액", text="소진액",
        labels={"소진액": "소진액 (억)", "월": "월"},
    )
    fig_credit.update_traces(
        marker_color=KT_RED, texttemplate="%{y}억", textposition="outside"
    )
    fig_credit.update_layout(
        height=300,
        title="2년차 월별 MACC 크레딧 소진 추이",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    st.plotly_chart(fig_credit, use_container_width=True)

# ── 탭4: 그룹사별 현황 ────────────────────────────────────────
with tab_company:
    st.markdown("##### 그룹사별 당월 현황")
    t_main, t_sub = st.tabs(["KT본체", "그룹사"])
    with t_main:
        if KT_MAIN in sel_companies:
            tbl_main = build_company_table([KT_MAIN], sel_month, prev_month)
            st.dataframe(
                style_company_table(tbl_main),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("KT본체가 필터에서 제외되었습니다.")
    with t_sub:
        subs = [c for c in SUBSIDIARIES if c in sel_companies]
        if subs:
            tbl_sub = build_company_table(subs, sel_month, prev_month)
            st.dataframe(
                style_company_table(tbl_sub),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("표시할 그룹사가 없습니다.")

    st.markdown("##### 월별 매출(청구액) 추이")
    trend = (
        usage_df[usage_df["그룹사"].isin(sel_companies)]
        .groupby("월", as_index=False)["Azure원가"]
        .sum()
    )
    trend["청구액_억"] = trend["Azure원가"].apply(billing) / 1e8
    fig_trend = px.line(
        trend,
        x="월",
        y="청구액_억",
        markers=True,
        labels={"청구액_억": "청구액 (억원)", "월": "월"},
    )
    fig_trend.update_traces(line_color=KT_RED, marker_color=KT_RED)
    fig_trend.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_trend, use_container_width=True)

# ── 탭5: 이상징후 ─────────────────────────────────────────────
with tab_alert:
    st.markdown("##### 전월 대비 30% 이상 급증 그룹사")
    spikes = get_spike_companies(sel_month, prev_month)
    if spikes:
        for item in spikes:
            st.markdown(
                f'<div class="banner-expiry">'
                f"<b>{item['그룹사']}</b> — 당월 {item['당월원가']} · "
                f"증감 <strong style='color:{KT_RED}'>{item['증감률']}</strong>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.success("30% 이상 급증 그룹사가 없습니다.")

    st.markdown("##### 예산 80% 초과 항목")
    budget_alert = get_budget_alerts(budget_df, sel_companies, mi, months)
    if not budget_alert.empty:
        st.dataframe(
            style_budget_table(budget_alert),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("예산 80%를 초과한 항목이 없습니다.")

st.caption(
    "목업 데이터 · CAPT 1조3,650억(2024.09~2029.09) · "
    f"크레딧 3년 400억 · MSP 마진 {MARGIN_PCT}% · GPU 핵심 매출"
)
