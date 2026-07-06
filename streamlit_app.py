import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title="Ringostat Deals Dashboard", layout="wide")

# Завантаження даних
DATA_PATH = Path(__file__).parent / "deals.csv"


@st.cache_data
def load_data(path_or_buffer):
    df = pd.read_csv(path_or_buffer)
    df.columns = [c.strip() for c in df.columns]

    df["AQL date"] = pd.to_datetime(df["AQL date"], errors="coerce")
    df["Closing Date"] = pd.to_datetime(df["Closing Date"], errors="coerce")

    # Нормалізація PPC budget: приводимо все до текстових "кошиків"
    def norm_ppc(v):
        if pd.isna(v):
            return "0"
        s = str(v).strip()
        if s in ("0", "0.0"):
            return "0"
        return s

    df["PPC budget bucket"] = df["PPC budget USD"].apply(norm_ppc)

    ppc_order = [
        "0",
        "0-500",
        "500-1000",
        "1000-2000",
        "2000-5000",
        "5000-10000",
        "20000+",
    ]
    present = [b for b in ppc_order if b in df["PPC budget bucket"].unique()]
    extra = [b for b in df["PPC budget bucket"].unique() if b not in present]
    df["PPC budget bucket"] = pd.Categorical(
        df["PPC budget bucket"], categories=present + extra, ordered=True
    )

    df["Client country"] = df["Client country"].fillna("Unknown")
    df["Client CRM"] = df["Client CRM"].fillna("Unknown")
    df["Source"] = df["Source"].fillna("Unknown")
    df["Stage"] = df["Stage"].fillna("Unknown")

    return df


if DATA_PATH.exists():
    df = load_data(DATA_PATH)
else:
    st.warning(
        "Файл deals.csv не знайдено поруч зі скриптом. Завантажте CSV/XLSX вручну."
    )
    uploaded = st.file_uploader("Завантажте файл з даними (CSV)", type=["csv"])
    if uploaded is None:
        st.stop()
    df = load_data(uploaded)

# Sidebar фільтри
st.sidebar.header("Фільтри")

countries = sorted(df["Client country"].unique())
selected_countries = st.sidebar.multiselect(
    "Client country", countries, default=countries
)

crms = sorted(df["Client CRM"].unique())
selected_crms = st.sidebar.multiselect("Client CRM", crms, default=crms)

min_date = df["AQL date"].min()
max_date = df["AQL date"].max()
date_range = st.sidebar.date_input(
    "Date range (AQL date)",
    value=(min_date.date(), max_date.date()),
    min_value=min_date.date(),
    max_value=max_date.date(),
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date.date(), max_date.date()

mask = (
    df["Client country"].isin(selected_countries)
    & df["Client CRM"].isin(selected_crms)
    & (df["AQL date"].dt.date >= start_date)
    & (df["AQL date"].dt.date <= end_date)
)
fdf = df[mask].copy()

st.title("📊 Ringostat Deals Dashboard")
st.caption(f"Угод у вибірці: **{len(fdf)}** з {len(df)}")

if fdf.empty:
    st.info("Немає даних для обраних фільтрів.")
    st.stop()


# Допоміжна функція win rate
def win_rate_table(data: pd.DataFrame, group_col: str) -> pd.DataFrame:
    closed = data[data["Stage"].isin(["Closed Won", "Closed Lost"])]
    grp = closed.groupby(group_col)["Stage"].value_counts().unstack(fill_value=0)
    for col in ["Closed Won", "Closed Lost"]:
        if col not in grp.columns:
            grp[col] = 0
    grp["Total closed"] = grp["Closed Won"] + grp["Closed Lost"]
    grp["Win rate %"] = (grp["Closed Won"] / grp["Total closed"] * 100).round(1)
    grp = grp.reset_index().sort_values("Win rate %", ascending=False)
    return grp[grp["Total closed"] > 0]


# Ряд 1: Win rate по країнах / по CRM
col1, col2 = st.columns(2)

with col1:
    st.subheader("Win rate по країнах")
    wr_country = win_rate_table(fdf, "Client country")
    fig = px.bar(
        wr_country,
        x="Win rate %",
        y="Client country",
        orientation="h",
        text="Win rate %",
        hover_data=["Closed Won", "Closed Lost", "Total closed"],
        color="Win rate %",
        color_continuous_scale="Blues",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=450)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Win rate по CRM")
    wr_crm = win_rate_table(fdf, "Client CRM")
    fig = px.bar(
        wr_crm,
        x="Win rate %",
        y="Client CRM",
        orientation="h",
        text="Win rate %",
        hover_data=["Closed Won", "Closed Lost", "Total closed"],
        color="Win rate %",
        color_continuous_scale="Greens",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=450)
    st.plotly_chart(fig, use_container_width=True)

# Ряд 2: Розподіл по Stage / Deals by Source
col3, col4 = st.columns(2)

with col3:
    st.subheader("Розподіл угод по Stage")
    stage_counts = fdf["Stage"].value_counts().reset_index()
    stage_counts.columns = ["Stage", "Count"]
    fig = px.pie(stage_counts, names="Stage", values="Count", hole=0.4)
    fig.update_traces(textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)

with col4:
    st.subheader("Кількість Deals by Source")
    source_counts = fdf["Source"].value_counts().reset_index()
    source_counts.columns = ["Source", "Count"]
    fig = px.bar(
        source_counts.sort_values("Count"),
        x="Count",
        y="Source",
        orientation="h",
        text="Count",
        color="Count",
        color_continuous_scale="Purples",
    )
    fig.update_layout(height=450)
    st.plotly_chart(fig, use_container_width=True)

# Ряд 3: Win rate vs PPC budget
st.subheader("Залежність win rate від PPC budget")
wr_ppc = win_rate_table(fdf, "PPC budget bucket")
wr_ppc = wr_ppc.sort_values("PPC budget bucket")

fig = px.bar(
    wr_ppc,
    x="PPC budget bucket",
    y="Win rate %",
    text="Win rate %",
    hover_data=["Closed Won", "Closed Lost", "Total closed"],
    color="Win rate %",
    color_continuous_scale="Oranges",
)
fig.update_layout(height=450)
st.plotly_chart(fig, use_container_width=True)

# Data quality checks
st.subheader("🩺 Data issues")
st.caption(
    "Перевірка якості даних по всьому датасету (незалежно від фільтрів). "
    "«Row» — номер рядка у deals.csv (з урахуванням заголовка)."
)


def data_quality_issues(data: pd.DataFrame) -> pd.DataFrame:
    d = data.reset_index(drop=True).copy()
    d["Row"] = d.index + 2  # +1 за заголовок, +1 щоб рахунок починався з 1

    closed = d["Stage"].isin(["Closed Won", "Closed Lost"])
    open_stage = ~closed & d["Stage"].ne("Unknown")

    checks = [
        (
            "Closed Won/Lost, але Closing Date порожня",
            closed & d["Closing Date"].isna(),
        ),
        (
            "Відкрита угода, але вказана Closing Date",
            open_stage & d["Closing Date"].notna(),
        ),
        (
            "Closed Lost без Loss reason",
            d["Stage"].eq("Closed Lost") & d["Loss reason description"].isna(),
        ),
        (
            "Closed Won, але заповнена Loss reason",
            d["Stage"].eq("Closed Won") & d["Loss reason description"].notna(),
        ),
        (
            "Closing Date раніше за AQL date",
            d["AQL date"].notna()
            & d["Closing Date"].notna()
            & (d["Closing Date"] < d["AQL date"]),
        ),
        ("Відсутня AQL date", d["AQL date"].isna()),
        (
            "Некоректна к-сть sales reps (порожня або ≤ 0)",
            d["Number of sales reps"].isna() | (d["Number of sales reps"] <= 0),
        ),
        ("Невідомий / порожній Stage", d["Stage"].eq("Unknown")),
    ]

    show_cols = [
        "Row",
        "AQL date",
        "Stage",
        "Closing Date",
        "Source",
        "Client CRM",
        "Client country",
        "Number of sales reps",
        "Loss reason description",
    ]

    parts = []
    for name, mask_check in checks:
        hit = d.loc[mask_check.fillna(False), show_cols].copy()
        if not hit.empty:
            hit.insert(0, "Issue", name)
            parts.append(hit)

    summary = pd.DataFrame(
        {
            "Перевірка": [name for name, m in checks],
            "Проблемних рядків": [int(m.fillna(False).sum()) for name, m in checks],
        }
    )

    detail = (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame(columns=["Issue"] + show_cols)
    )
    return summary, detail


qc_summary, qc_detail = data_quality_issues(df)
total_issues = int(qc_summary["Проблемних рядків"].sum())

if total_issues == 0:
    st.success("✅ Проблем з якістю даних не знайдено.")
else:
    st.warning(f"⚠️ Знайдено проблемних записів: **{total_issues}**")
    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.markdown("**Зведення**")
        st.dataframe(
            qc_summary.sort_values("Проблемних рядків", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
    with col_b:
        st.markdown("**Деталізація (проблемні рядки)**")
        issue_options = qc_detail["Issue"].unique().tolist()
        selected_issues = st.multiselect(
            "Фільтр за типом проблеми",
            issue_options,
            default=issue_options,
        )
        st.dataframe(
            qc_detail[qc_detail["Issue"].isin(selected_issues)],
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "⬇️ Завантажити Data issues (CSV)",
            qc_detail.to_csv(index=False).encode("utf-8-sig"),
            file_name="data_issues.csv",
            mime="text/csv",
        )

# Таблиця з деталями
with st.expander("Показати відфільтровані дані (таблиця)"):
    st.dataframe(fdf, use_container_width=True)
