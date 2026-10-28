"""工作台的布局与视觉样式；不包含评分、预测或优化逻辑。"""
import streamlit as st


WORKSPACE_TABS = ["Campaign 总览", "KOL 数据库", "投放组合优化", "情景分析", "报告与导出"]


def apply_workspace_style():
    # 只调整外观；保留 Streamlit 原生控件、键盘导航和表格滚动。
    st.html("""
    <style>
    :root { --kol-accent: #163f3c; --kol-ink: #1d3039; --kol-muted: #64747c; }
    .stApp { background: #f3f6f7; color: var(--kol-ink); font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
    [data-testid="stMainBlockContainer"] { max-width: 1440px; padding-top: 2rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e2e8f0; }
    [data-testid="stSidebar"] h2 { font-size: 1.05rem; }
    h1 { font-size: clamp(1.4rem, 2.1vw, 2rem) !important; letter-spacing: -.035em; font-weight: 750 !important; overflow-wrap: anywhere; }
    h2, h3 { color: var(--kol-ink); letter-spacing: -.02em; }
    h3 { font-size: 1.15rem !important; padding-top: .75rem !important; }
    [data-testid="stCaptionContainer"] { color: var(--kol-muted); }
    [data-testid="stMetric"] { background: #fff; border: 1px solid #dce4e6; border-radius: 6px; padding: .85rem 1rem; }
    [data-testid="stMetricLabel"] { color: var(--kol-muted); font-size: .85rem; }
    [data-testid="stMetricValue"] { color: var(--kol-ink); font-variant-numeric: tabular-nums; font-size: clamp(1.4rem, 2vw, 1.9rem); }
    [data-testid="stTabs"] [role="tablist"] { gap: .5rem; border-bottom: 1px solid #dce3ee; overflow-x: auto; }
    [data-testid="stTabs"] [role="tab"] { padding: .75rem 1rem; height: auto; white-space: nowrap; color: var(--kol-muted); }
    [data-testid="stTabs"] [aria-selected="true"] { color: var(--kol-accent); font-weight: 650; }
    [data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: var(--kol-accent); }
    [data-testid="stExpander"] { background: #fff; border-radius: 7px; }
    [data-testid="stDataFrame"] { border-radius: 6px; border: 1px solid #dce4e6; }
    [data-testid="stAlert"] { border-radius: 6px; }
    [data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) { background: #eaf3ef; color: #163f3c; border: 1px solid #d4e5de; }
    [data-testid="stButton"] button, [data-testid="stDownloadButton"] button { border-radius: 5px; font-weight: 600; }
    [data-testid="stButton"] button[kind="primary"], [data-testid="stDownloadButton"] button[kind="primary"] { background: #163f3c; border-color: #163f3c; color: #fff; }
    [data-testid="stButton"] button[kind="primary"]:hover, [data-testid="stDownloadButton"] button[kind="primary"]:hover { background: #265e57; border-color: #265e57; }
    [data-testid="stProgressBar"] [role="progressbar"] { accent-color: #207968; }
    div[class*="st-key-panel_"] { background: #fff; border-radius: 7px; }
    .st-key-overview_intro { background: #eaf3ef; border-radius: 7px; border-color: #d4e5de; }
    div[class*="st-key-feature_"] { background: #fff; border-radius: 7px; }
    a { color: #207968; }
    @media (max-width: 900px) {
      [data-testid="stMainBlockContainer"] { padding: 1.25rem 1rem 2rem; }
      [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .75rem; }
      [data-testid="stColumn"] { min-width: min(190px, 100%); flex: 1 1 190px; }
      [data-testid="stTabs"] [role="tab"] { padding: .6rem .7rem; }
    }
    </style>
    """)


def render_metrics(metrics, labels, columns_per_row=4):
    """只格式化已有计算结果；不更改数值或单位。"""
    entries = list(labels.items())
    for start in range(0, len(entries), columns_per_row):
        columns = st.columns(min(columns_per_row, len(entries) - start))
        for column, (key, caption) in zip(columns, entries[start:start + columns_per_row]):
            value = metrics[key]
            formatted = "不适用" if value is None else (str(int(value)) if key == "creator_count" else f"{value:,.2f}")
            column.metric(caption, formatted)


def open_workspace(tab_label):
    """首页入口只切换原生标签，不新建会话或重复执行业务流程。"""
    st.session_state['workspace_view'] = tab_label


def render_feature_entries():
    entries = [
        ("01", "KOL 数据库", "核对公开来源与模拟参数，筛选并比较候选评分。", "筛选候选"),
        ("02", "投放组合优化", "查看预算内的创作者组合、预测效果与选择取舍。", "查看推荐组合"),
        ("03", "情景分析", "保存基准后调整预算或目标，比较方案的变化。", "比较方案"),
        ("04", "报告与导出", "复核当前方案、计算假设与风险，再下载 CSV。", "查看报告"),
    ]
    st.subheader("开始你的决策流程")
    for offset in (0, 2):
        columns = st.columns(2, gap="medium")
        for column, (number, title, description, action) in zip(columns, entries[offset:offset + 2]):
            with column.container(border=True, key=f"feature_{number}"):
                st.caption(f"{number} / 决策工作流")
                st.markdown(f"**{title}**")
                st.caption(description)
                st.button(action, key=f"go_module_{number}", on_click=open_workspace,
                          args=(title,), type="primary")


def detail_columns(section):
    """主内容/辅助信息两栏，窄屏由原生列及媒体规则换行。"""
    main, aside = st.columns([3.2, 1.15], gap="large")
    return (main.container(border=True, key=f"panel_{section}_main"),
            aside.container(border=True, key=f"panel_{section}_aside"))


def render_campaign_context(brand, market, objective):
    st.markdown("**当前 Campaign**")
    st.write(brand or "（未填写品牌）")
    st.caption(f"{market or '（未指定市场）'} · {objective}")
    st.caption("活动参数在左侧统一调整；所有区域使用同一组输入。")
