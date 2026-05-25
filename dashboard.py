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

    # C-Plan 2년차 월별 (억)
    y2_months = [
        "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
        "2026-03", "2026-04", "2026-05",
    ]
    monthly_burn = [95, 102, 98, 105, 99, 101, 100, 100]  # 합 800억
    pace = CPLAN_Y2_TARGET / 12
    cplan_y2 = pd.DataFrame({
        "월": y2_months,
        "누적실적": np.cumsum(monthly_burn),
        "누적페이스": [pace * (i + 1) for i in range(8)],
    })

    # 크레딧 월별 소진 (2년차, 억)
    credit_burn = pd.DataFrame({
        "월": y2_months,
        "소진액": [12, 11, 10, 9, 10, 9, 8, 6],
    })
    credit_y2_used = 75  # 억, 120억 중
    credit_y2_remain = CREDIT_Y2 - credit_y2_used

    return {
        "usage": usage_df,
        "gpu": gpu_df,
        "ri": ri_df,
        "cplan_y2": cplan_y2,
        "credit_burn": credit_burn,
        "credit_y2_remain": credit_y2_remain,
        "credit_y2_used": credit_y2_used,
        "months": months,
    }


# ── 데이터 ─────────────────────────────────────────────────────
data = generate_data()
usage_df = data["usage"]
gpu_df = data["gpu"]
ri_df = data["ri"]
cplan_y2 = data["cplan_y2"]
credit_burn = data["credit_burn"]
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

# ══════════════════════════════════════════════════════════════
# 섹션1 — 핵심 KPI 6개
# ══════════════════════════════════════════════════════════════
st.subheader("① 핵심 KPI")

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

st.markdown(
    f'<p>C-Plan 2년차 신호등: <span class="{cplan_cls}">{cplan_signal}</span> '
    f"(누적 {CPLAN_Y2_CUMULATIVE}억 / 8개월 페이스 대비 {cplan_rate:.1f}%)</p>",
    unsafe_allow_html=True,
)
st.divider()

# ══════════════════════════════════════════════════════════════
# 섹션2 — GPU 현황 (메인)
# ══════════════════════════════════════════════════════════════
st.subheader("② GPU 현황")

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
                fig_g.update_layout(height=220, margin=dict(l=20, r=20, t=50, b=10))
                st.plotly_chart(fig_g, use_container_width=True)
    else:
        st.info("예약 인스턴스 데이터 없음")

    st.markdown("##### 유휴 GPU 리소스 (절감 가능)")
    idle = gpu_month[gpu_month["유휴VM"] > 0].copy()
    if not idle.empty:
        idle["월절감가능액"] = (
            idle["유휴VM"] * idle["시간당단가"] * 730
        )
        idle_tbl = (
            idle.groupby(["그룹사", "GPU_VM종류"], as_index=False)
            .agg(
                유휴VM=("유휴VM", "sum"),
                절감가능금액=("월절감가능액", "sum"),
            )
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

st.divider()

# ══════════════════════════════════════════════════════════════
# 섹션3 — C-Plan
# ══════════════════════════════════════════════════════════════
st.subheader("③ C-Plan 달성 현황")

c1, c2 = st.columns(2)

with c1:
    st.markdown("##### 연도별 목표 vs 실적")
    y1_rate = CPLAN_Y1_ACTUAL / CPLAN_Y1_TARGET * 100
    y2_rate = CPLAN_Y2_CUMULATIVE / (CPLAN_Y2_TARGET / 12 * 8) * 100
    cplan_annual = pd.DataFrame({
        "연차": ["1년차\n(24.10~25.09)", "2년차\n(25.10~26.09)\n8개월"],
        "목표": [CPLAN_Y1_TARGET, CPLAN_Y2_TARGET / 12 * 8],
        "실적": [CPLAN_Y1_ACTUAL, CPLAN_Y2_CUMULATIVE],
    })
    fig_cplan = go.Figure()
    fig_cplan.add_trace(
        go.Bar(
            name="목표",
            x=cplan_annual["연차"],
            y=cplan_annual["목표"],
            marker_color="#d1d5db",
        )
    )
    fig_cplan.add_trace(
        go.Bar(
            name="실적",
            x=cplan_annual["연차"],
            y=cplan_annual["실적"],
            marker_color=KT_RED,
            text=cplan_annual["실적"].apply(lambda v: f"{v:.0f}억"),
            textposition="outside",
        )
    )
    fig_cplan.update_layout(
        barmode="group",
        height=340,
        yaxis_title="억원",
        legend=dict(orientation="h", y=1.12),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig_cplan, use_container_width=True)
    s1, s1c = signal_class(y1_rate)
    s2, s2c = signal_class(y2_rate)
    st.markdown(
        f"1년차 달성률 {y1_rate:.1f}% <span class='{s1c}'>{s1}</span> · "
        f"2년차(8M) {y2_rate:.1f}% <span class='{s2c}'>{s2}</span>",
        unsafe_allow_html=True,
    )

with c2:
    st.markdown("##### 2년차 월별 누적 vs C-Plan 페이스")
    fig_pace = go.Figure()
    fig_pace.add_trace(
        go.Scatter(
            x=cplan_y2["월"],
            y=cplan_y2["누적페이스"],
            name="C-Plan 페이스",
            mode="lines+markers",
            line=dict(color="#9ca3af", dash="dash"),
        )
    )
    fig_pace.add_trace(
        go.Scatter(
            x=cplan_y2["월"],
            y=cplan_y2["누적실적"],
            name="누적 실적",
            mode="lines+markers",
            line=dict(color=KT_RED, width=3),
        )
    )
    fig_pace.update_layout(
        height=340,
        yaxis_title="누적 (억원)",
        margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_pace, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════
# 섹션4 — 크레딧
# ══════════════════════════════════════════════════════════════
st.subheader("④ 크레딧 현황")

cr1, cr2, cr3 = st.columns(3)
with cr1:
    st.metric("1년차 (160억)", "소진 완료", delta="100%")
with cr2:
    remain = data["credit_y2_remain"]
    st.metric(
        "2년차 (120억)",
        "진행 중",
        delta=f"잔여 {format_억(remain, 0)}",
    )
with cr3:
    st.metric("3년차 (120억)", "미수령", delta="0%")

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
    credit_burn,
    x="월",
    y="소진액",
    text="소진액",
    labels={"소진액": "소진액 (억)", "월": "월"},
)
fig_credit.update_traces(marker_color=KT_RED, texttemplate="%{y}억", textposition="outside")
fig_credit.update_layout(
    height=280,
    title="2년차 월별 크레딧 소진 추이",
    margin=dict(l=10, r=10, t=40, b=10),
)
st.plotly_chart(fig_credit, use_container_width=True)

st.divider()

# ══════════════════════════════════════════════════════════════
# 섹션5 — 그룹사별 현황 테이블
# ══════════════════════════════════════════════════════════════
st.subheader("⑤ 그룹사별 현황")

def build_company_table(companies: list[str]) -> pd.DataFrame:
    rows = []
    for co in companies:
        cur = usage_df[
            (usage_df["그룹사"] == co) & (usage_df["월"] == sel_month)
        ]["Azure원가"].sum()
        prv = (
            usage_df[
                (usage_df["그룹사"] == co) & (usage_df["월"] == prev_month)
            ]["Azure원가"].sum()
            if prev_month
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


def style_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    show = df.drop(columns=["_증감수치"])

    def highlight(row):
        chg = df.at[row.name, "_증감수치"]
        if chg >= 30:
            css = f"background-color:#ffe4e4;color:{KT_RED};font-weight:600"
            return [css] * len(row)
        return [""] * len(row)

    return show.style.apply(highlight, axis=1)


tab_main, tab_sub = st.tabs(["KT본체", "그룹사"])

with tab_main:
    if KT_MAIN in sel_companies:
        tbl_main = build_company_table([KT_MAIN])
        st.dataframe(style_table(tbl_main), use_container_width=True, hide_index=True)
    else:
        st.info("KT본체가 필터에서 제외되었습니다.")

with tab_sub:
    subs = [c for c in SUBSIDIARIES if c in sel_companies]
    if subs:
        tbl_sub = build_company_table(subs)
        spike = tbl_sub[tbl_sub["_증감수치"] >= 30]
        st.dataframe(style_table(tbl_sub), use_container_width=True, hide_index=True)
        if not spike.empty:
            st.markdown(
                f'<div class="banner-expiry" style="margin-top:8px">'
                f"⚠️ 전월 대비 30% 이상 급증: "
                f"<strong>{', '.join(spike['그룹사명'].tolist())}</strong>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("표시할 그룹사가 없습니다.")

st.caption(
    "목업 데이터 · CAPT 1조3,650억(2024.09~2029.09) · "
    f"크레딧 3년 400억 · MSP 마진 {MARGIN_PCT}% · GPU 핵심 매출"
)
