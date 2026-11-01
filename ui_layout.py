"""工作台的布局与视觉样式；不包含评分、预测或优化逻辑。"""
import streamlit as st
import pandas as pd
import math

CHART_COLORS = ['#207968', '#d18a36', '#4e79a7', '#8b8f98', '#76a994', '#b18bc2']
OUTCOME_LABELS = {'target_reach': '触达（人次，未去重）', 'engagements': '互动（次）',
                  'clicks': '点击（次）', 'conversions': '转化（模拟期望数）'}


def value_chart(frame, category, value, title, unit, group=None, line=False, horizontal=False, stack=None):
    """Display provided values only; null values are omitted, never imputed."""
    if frame.empty or value not in frame or frame[value].notna().sum() == 0:
        return
    clean = frame.loc[frame[value].notna()].copy()
    quantitative = {'field': value, 'type': 'quantitative', 'title': unit, 'scale': {'zero': True},
                    'axis': {'tickCount':5,'labelPadding':8,'titlePadding':16}}
    categorical = {'field': category, 'type': 'ordinal', 'title': '预算（USD）' if category == '预算' else category, 'sort': None,
                   'axis': {'labelAngle': 0, 'labelPadding': 10, 'titlePadding': 16,
                            'labelLimit':0,'labelOverlap':False,'labelExpr': "split(datum.label, ' ')"}}
    encoding = {'x': quantitative if horizontal else categorical,
                'y': categorical if horizontal else quantitative,
                'tooltip': [{'field': category}, {'field': value, 'type': 'quantitative', 'title': unit}]}
    if group:
        encoding['color'] = {'field': group, 'type': 'nominal', 'title': group, 'scale': {'range': CHART_COLORS},
                             'legend': {'orient':'bottom','direction':'vertical','labelLimit':0,'titlePadding':10,'offset':18}}
        if stack:
            encoding['y']['stack'] = 'zero'
        elif not line:
            encoding['yOffset' if horizontal else 'xOffset'] = {'field': group}
        encoding['tooltip'].append({'field': group})
    st.markdown('**' + title + '**')
    legend_rows = clean[group].nunique() if group else 0
    # Streamlit fits the entire chart (including axes/legend) into this height.
    chart_height = max(360, clean[category].nunique()*44+140+legend_rows*24) if horizontal else 340+legend_rows*24
    st.vega_lite_chart(clean, {'height': chart_height, 'padding': {'top':16,'bottom':16,'left':16,'right':16},
        'config': {'axis': {'labelFontSize':12,'titleFontSize':12,'titlePadding':16},'view':{'stroke':None}},
        'mark': {'type': 'line', 'point': True} if line else {'type': 'bar', 'color': '#4e79a7' if title.startswith('第三方报告') else CHART_COLORS[0]},
        'encoding': encoding}, width='stretch')


def outcome_charts(frame, category, title, group=None, line=False):
    """Three separate axes avoid mixing reach, engagements and conversions."""
    st.caption(title + ' · Simulation；各指标独立坐标轴。')
    for col, metric in zip(st.columns(3), ('target_reach', 'engagements', 'conversions')):
        with col:
            value_chart(frame, category, metric, 'Simulation · ' + OUTCOME_LABELS[metric], OUTCOME_LABELS[metric], group, line)


def comparison_charts(accounts, scores, ids, dimensions):
    selected = accounts.loc[accounts.creator_id.isin(ids)].copy()
    st.caption('🔵 第三方报告指标；不是模拟触达或广告表现。空白值显示未提供，不作零值替代。')
    fields = [('reported_followers','粉丝/订阅数','人'), ('reported_mean_views','平均播放','次'),
              ('reported_median_views','中位播放','次'), ('reported_mean_engagement_rate','报告互动率','%')]
    for index, (field, label, unit) in enumerate(fields):
        if index % 2 == 0:
            columns = st.columns(2)
        with columns[index % 2]:
            data = selected[['handle', field]].copy()
            if field.endswith('rate'):
                data[field] = data[field] * 100
            value_chart(data, 'handle', field, '第三方报告 · ' + label, unit, horizontal=True)
            for row in data.itertuples(index=False, name=None):
                if pd.isna(row[1]):
                    st.caption(f'@{row[0]}：未提供')
            if len(data) == 2 and data[field].notna().all():
                st.caption(f'两人差额（表内前者−后者）：{data.iloc[0][field] - data.iloc[1][field]:,.2f} {unit}')
    # Polar coordinates are display geometry, not a prediction or scoring model.
    chosen = scores.loc[scores.creator_id.isin(ids)]
    angles = [-math.pi/2 + i*2*math.pi/5 for i in range(5)]
    def point(angle, radius):
        return dict(x=radius*math.cos(angle), y=-radius*math.sin(angle))
    grid, labels, points, complete = [], [], [], []
    for radius in (30,60,90):
        grid.extend(dict(**point(a,radius), path=str(radius), order=i) for i,a in enumerate(angles+[angles[0]]))
    for i,(angle,label) in enumerate(zip(angles,dimensions)):
        grid.extend([dict(x=0,y=0,path='axis'+str(i),order=0),dict(**point(angle,90),path='axis'+str(i),order=1)])
        labels.append(dict(**point(angle,125),label=label))
    for _, row in chosen.iterrows():
        values = [row[d] for d in dimensions]
        name = row.creator_id+' @'+row.handle
        known = [dict(**point(a,float(v)*.9),达人=name,维度=d,得分=float(v),order=i) for i,(a,v,d) in enumerate(zip(angles,values,dimensions)) if pd.notna(v)]
        points.extend(known)
        if all(pd.notna(v) for v in values):
            complete.extend(known+[dict(known[0],order=5)])
        missing = [d for d,v in zip(dimensions,values) if pd.isna(v)]
        st.caption(name+'：'+('未提供：'+'、'.join(missing) if missing else '五维齐全'))
    xy={'x':{'field':'x','type':'quantitative','axis':None,'scale':{'domain':[-175,175]}},
        'y':{'field':'y','type':'quantitative','axis':None,'scale':{'domain':[-155,155]}}}
    color={'field':'达人','type':'nominal','scale':{'range':CHART_COLORS},
           'legend':{'orient':'bottom','direction':'vertical','labelLimit':0,'offset':18}}
    layers=[{'data':{'values':grid},'mark':{'type':'line','stroke':'#dce4e6'},'encoding':dict(xy,detail={'field':'path'},order={'field':'order'})},
            {'data':{'values':labels},'mark':{'type':'text','fontSize':12},'encoding':dict(xy,text={'field':'label'})}]
    if complete:
        layers.append({'data':{'values':complete},'mark':{'type':'line'},'encoding':dict(xy,color=color,detail={'field':'达人'},order={'field':'order'})})
    layers.append({'data':{'values':points},'mark':{'type':'point','filled':True,'size':65},'encoding':dict(xy,color=color,tooltip=[{'field':'达人'},{'field':'维度'},{'field':'得分'}])})
    st.markdown('**五维评分雷达 · 0–100分（外圈100，内圈约33/67）**')
    with st.container(width=420):
        st.vega_lite_chart({'height':480,'padding':{'top':20,'bottom':20,'left':20,'right':20},'autosize':{'type':'fit','contains':'padding'},'layer':layers},width='stretch')
    st.caption('不完整评分仅显示已知点，不绘制闭合区域。适配/证据依据见文字说明；预算效率来自Simulation。')


def portfolio_change_charts(before, after, title):
    st.markdown('**' + title + ' · Simulation**')
    for col, label, result in zip(st.columns(2), ('原组合','新组合'), (before,after)):
        with col:
            st.metric(label + '支出（模拟USD）', f"${result.metrics['spent_usd']:,.2f}",
                      delta=f"${after.metrics['spent_usd']-before.metrics['spent_usd']:,.2f}" if label=='新组合' else None)
            st.caption('、'.join(result.selected.get('creator_id', [])) or '无入选达人')
    outcomes = pd.DataFrame([dict(方案='原组合',**before.metrics),dict(方案='新组合',**after.metrics)])
    outcome_charts(outcomes,'方案','新旧组合效果')
    value_chart(outcomes,'方案','clicks','Simulation · 点击变化','次')
    st.caption('柱高为各方案实际计算值；差额与进入/退出名单见原有解释，不代表真实投放结果。')


WORKSPACE_TABS = ["Campaign 总览", "KOL 数据库", "投放组合优化", "情景分析", "报告与导出"]


def apply_workspace_style():
    # 只调整外观；保留 Streamlit 原生控件、键盘导航和表格滚动。
    st.html("""
    <style>
    :root { --kol-accent: #163f3c; --kol-ink: #1d3039; --kol-muted: #64747c; }
    .stApp { background: #f3f6f7; color: var(--kol-ink); font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
    [data-testid="stMainBlockContainer"] { max-width: 1440px; padding-top: 5rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e2e8f0; }
    [data-testid="stSidebar"] h2 { font-size: 1.05rem; }
    h1 { font-size: clamp(1.4rem, 2.1vw, 2rem) !important; letter-spacing: -.035em; font-weight: 750 !important; overflow-wrap: anywhere; }
    h2, h3 { color: var(--kol-ink); letter-spacing: -.02em; }
    h3 { font-size: 1.15rem !important; line-height: 1.5 !important; padding-top: .5rem !important; padding-bottom: .5rem !important; }
    [data-testid="stCaptionContainer"] { color: var(--kol-muted); }
    [data-testid="stMetric"] { background: #fff; border: 1px solid #dce4e6; border-radius: 6px; padding: .85rem 1rem; }
    [data-testid="stMetricLabel"] { color: var(--kol-muted); font-size: .85rem; height: auto; min-height: 1.5em; overflow: visible; }
    [data-testid="stMetricLabel"] p { white-space: normal; overflow: visible; line-height: 1.5; }
    [data-testid="stMetricValue"] { color: var(--kol-ink); font-variant-numeric: tabular-nums; font-size: clamp(1.4rem, 2vw, 1.9rem); height: auto; line-height: 1.5; overflow: visible; }
    [data-testid="stMetricValue"] > div { white-space: normal; overflow-wrap: anywhere; overflow: visible; }
    [data-testid="stTabs"] [role="tablist"] { gap: .5rem; border-bottom: 1px solid #dce3ee; height: auto; flex-wrap: wrap; overflow: visible; }
    [data-testid="stTabs"] [role="tab"] { padding: .75rem 1rem; height: auto; min-height: 3rem; white-space: normal; color: var(--kol-muted); }
    [data-testid="stTabs"] [role="tab"] p { white-space: normal; line-height: 1.5; }
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
    [data-testid="stMarkdownContainer"] { overflow-wrap: anywhere; word-break: normal; }
    [data-testid="stMarkdownContainer"] p { line-height: 1.65; }
    [data-testid="stTable"] table { table-layout: fixed; width: 100%; }
    [data-testid="stTable"] th, [data-testid="stTable"] td { white-space: normal; overflow-wrap: anywhere; vertical-align: middle; line-height: 1.65; padding: .75rem; height: auto; }
    [data-testid="stColumn"] { min-width: 0; }
    [data-testid="stVegaLiteChart"] { min-width: 0; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; }
    @media (max-width: 900px) {
      [data-testid="stMainBlockContainer"] { padding: 4.5rem 1rem 2rem; }
      [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .75rem; }
      [data-testid="stColumn"] { min-width: min(190px, 100%); flex: 1 1 190px; }
      [data-testid="stTabs"] [role="tab"] { padding: .6rem .7rem; }
    }
    @media (max-width: 1100px) {
      [data-testid="stColumn"]:has([data-testid="stVegaLiteChart"]) { flex: 1 1 100%; width: 100%; min-width: 100%; }
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
