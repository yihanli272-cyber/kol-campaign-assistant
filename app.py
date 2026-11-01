"""Campaign setup, creator scoring, portfolio planning and scenario comparison."""
import streamlit as st
from ui_layout import (WORKSPACE_TABS, apply_workspace_style, render_metrics, detail_columns,
                       render_feature_entries, render_campaign_context, open_workspace)

from kol_data import ASSUMPTION_VERSION, EFFICIENCY_CAPS, WEIGHTS, load_kol_data, score_kols
from portfolio import (DISCLAIMER, OUTCOME_COLUMNS, compare_scenarios, export_portfolio_csv,
                       make_snapshot, model_fingerprint, optimize_portfolio)
from ui_zh import (DISCLAIMER_ZH, campaign_zh, column_label, creator_reason_zh, label as zh_label,
                   selection_reason_zh, show_table, text_zh)
from research_data import (PARAMETER_MAP, load_campaign_assumptions, load_real_kols,
                           prepare_research_model, research_fingerprint)

st.set_option("client.toolbarMode", "minimal")
st.set_page_config(page_title="AI KOL Campaign Decision Assistant", page_icon="📊", layout="wide")
if st.query_params.get('workspace') != 'legacy':
    from sprint_ui import render_sprint
    render_sprint()
    st.stop()

st.warning('历史回归演示：此页面的历史模拟池不用于当前正式推荐。返回主地址（移除 workspace=legacy）进入52条真实账号工作台。')
apply_workspace_style()
st.title("AI KOL Campaign Decision Assistant")
st.caption("海外 KOL 营销决策工作台")

with st.sidebar:
    dataset = st.radio("数据集", ["Simulated Demo Dataset", "Real Creator Research Dataset"], format_func=zh_label, key="dataset")
    st.header("营销活动参数")
    brand = st.text_input("品牌", "PETKIT", max_chars=120)
    product = st.text_input("产品", "YumShare Dual-hopper 2", max_chars=200)
    market = st.text_input("目标市场", "美国", max_chars=100)
    objective = st.selectbox("营销目标", list(WEIGHTS), format_func=zh_label)
    budget = st.number_input("模拟总预算（美元）", min_value=0, max_value=10_000, value=5_000, step=100)
    with st.expander("执行成本与人数上限"):
        sample_usd = st.number_input("每位创作者样品成本（美元，假设）", min_value=0, max_value=10000, value=0, step=10)
        shipping_usd = st.number_input("每位创作者物流成本（美元，假设）", min_value=0, max_value=10000, value=0, step=10)
        max_creators = st.number_input("最多选择人数", min_value=1, max_value=6, value=6, step=1)
        st.caption("执行预算包含每位入选创作者的合作费、样品和物流成本。额外成本默认 $0，仅作占位；请按场景修改。")

try:
    is_research = dataset == "Real Creator Research Dataset"
    if is_research:
        research = load_real_kols()
        assumptions = load_campaign_assumptions()
        audit, data = prepare_research_model(research, assumptions)
        dataset_fingerprint = "research/" + research_fingerprint(research, assumptions)
    else:
        data = load_kol_data()
        dataset_fingerprint = "demo/" + model_fingerprint(data)
    scored = score_kols(data, objective) if not data.empty else data.copy()
except ValueError as exc:
    st.error(text_zh(str(exc)))
    st.stop()

if is_research:
    st.warning("真实身份＋模拟规划：公开资料仅部分核实，包含历史记录。匹配分、质量分、报价、触达、互动率、CTR、CVR 均为人为演示预设，不是创作者实测表现。具备建模参数不代表可预订或美国受众占多数。")
else:
    st.warning("仅为模拟数据：30 位创作者均为虚构。报价、受众匹配、触达、互动、内容质量和预测假设均为演示用途设定。")

overview_tab, database_tab, portfolio_tab, scenario_tab, report_tab = st.tabs(WORKSPACE_TABS, key="workspace_view", on_change="rerun")

with overview_tab:
    with st.container(border=True, key="overview_intro"):
        st.caption("从 Campaign 问题到预算决策")
        st.subheader("让每一份预算，都有可解释的选择")
        st.write("先核对创作者与数据口径，再查看预算内组合，最后通过情景比较复核方案。")
        st.caption("公开资料、人工评价与模拟投放假设分别标注；这里的预测不是实际投放结果。")
        st.button("查看当前推荐组合", key="go_portfolio", type="primary",
                  on_click=open_workspace, args=("投放组合优化",))
    with st.container(border=True, key="panel_campaign_overview"):
        st.subheader("活动与创作者")
        st.write(f"{brand or '（未填写品牌）'} · {product or '（未填写产品）'} · {market or '（未指定市场）'}")
        st.caption(f"目标：{zh_label(objective)} | 预算假设：${budget:,.0f} | 数据集：{zh_label(dataset)} | 假设版本： {assumptions.assumption_version.iloc[0] if is_research else ASSUMPTION_VERSION}")
        st.info("匹配分假设针对美国宠物科技场景。品牌、产品和市场名称仅作展示，不会自动校准评分。用于其他市场或行业前，须人工核实或替换假设。")

    overview_primary = st.container()
    with st.expander("数据集概况与样本统计"):
        cols = st.columns(4)
        if is_research:
            cols[0].metric("研究候选身份", len(research))
            cols[1].metric("模型参数完整的候选", len(data))
            cols[2].metric("有日期的粉丝观测", int(research.followers.notna().sum()))
            cols[3].metric("暂缓建模的候选", len(research) - len(data))
        else:
            cols[0].metric("模拟创作者", len(data))
            cols[1].metric("平台", data["platform"].nunique())
            cols[2].metric("粉丝数中位数", f"{data['followers'].median():,.0f}")
            cols[3].metric("模拟报价中位数", f"${data['estimated_fee_usd'].median():,.0f}")
            st.caption("全部样本摘要（30 条模拟记录）")
            show_table(data.groupby(["platform", "creator_category"]).size().rename("creators").reset_index(), hide_index=True)
            st.write(f"粉丝数：{data.followers.min():,}–{data.followers.max():,}；模拟报价：${data.estimated_fee_usd.min():,}–${data.estimated_fee_usd.max():,}；平均模拟互动率：{data.engagement_rate.mean():.1%}。")


with database_tab:
    database_main, database_aside = detail_columns("database")

with database_main:
    st.subheader("KOL 数据库")
    st.caption("先筛选候选，再查看评分；全部筛选条件同步用于组合优化。表格支持列排序与横向滚动。")
    if is_research:
        st.subheader("真实创作者候选池")
        st.write(f"公开身份 {len(research)} 个 · 演示模型参数完整 {len(data)} 个 · 暂不进入优化 {len(research) - len(data)} 个。")
        st.info("公开资料：身份、来源链接及带日期的观测。研究判断：内容分类与产品适配理由。模拟输入：数值评分与投放参数，另表存储。未知观测保持缺失；第三方近似粉丝数与有日期的观测分开保存。")
        with st.expander("公开研究资料与缺失字段", expanded=False):
            show_table(research, hide_index=True, width="stretch", column_config={
                "profile_url": st.column_config.LinkColumn("公开主页"),
                "source_url": st.column_config.LinkColumn("资料来源"),
                "recent_content_source_url": st.column_config.LinkColumn("第三方内容记录"),
            })
            st.caption("空白表示未知，不是 0。第三方近似粉丝数缺少单项测量日期；观测粉丝数仅保留有日期的快照。B 层级仍依赖二手证据。所有账号均未标为完全验证；候选名单不代表可实际合作的资源。")
        with st.expander("独立模拟参数与建模资格", expanded=False):
            show_table(audit[["creator_id", "creator_name", "verification_status", "model_eligible", "model_eligibility_reason"] + list(PARAMETER_MAP)], hide_index=True, width="stretch")
            st.caption("只有明确启用建模、参数完整有效且每项都有来源说明的候选才能进入计算。未启用的记录不会自动补齐数值。")
            show_table(assumptions, hide_index=True, width="stretch")
            st.caption("5 个启用账号共用同一演示模板：报价 $500、触达 20,000、互动率 5%、CTR 2%、CVR 2%、匹配分和质量分各 70。该模板不用于判断真实创作者的表现优劣；其余 25 个须先复核并明确配置参数。")
    with st.expander("创作者筛选", expanded=True):
        left, right = st.columns(2)
        platforms = left.multiselect("平台", sorted(data.platform.unique()), default=sorted(data.platform.unique()))
        categories = right.multiselect("内容分类", sorted(data.creator_category.unique()), default=sorted(data.creator_category.unique()), format_func=zh_label)
        left, middle, right = st.columns(3)
        min_followers = left.number_input("最低粉丝数", min_value=0, max_value=10_000_000, value=0, step=1000)
        if is_research:
            st.caption("研究模式仅对具备完整模型参数的候选排序。最低粉丝数为 0 时保留未知观测；设置为正数会排除未知值，不补造模拟粉丝数。")
        min_engagement = middle.slider("最低模型互动率（%）", 0.0, 10.0, 0.0, 0.5)
        min_match = right.slider("最低受众匹配分", 0, 100, 0)
        max_fee = left.number_input("最高模拟报价（美元）", min_value=0, value=6000, step=100)
        min_quality = middle.slider("最低内容质量分", 0, 100, 0)
        budget_only = right.checkbox("仅保留报价在单人预算内的候选", value=False)


fee_limit = min(max_fee, budget) if budget_only else max_fee
follower_filter = scored.followers.ge(min_followers)
if is_research and min_followers == 0:
    follower_filter = follower_filter | scored.followers.isna()
filtered = scored.loc[
    scored.platform.isin(platforms) & scored.creator_category.isin(categories)
    & follower_filter & scored.engagement_rate.ge(min_engagement / 100)
    & scored.audience_match_score.ge(min_match) & scored.content_quality_score.ge(min_quality)
    & scored.estimated_fee_usd.le(fee_limit)
]

with database_main:
    st.subheader(f"创作者排序 · {len(filtered)} / {len(data)}")
    st.caption("综合评分越高，排名越靠前。" + ("身份来自公开研究；非空的粉丝数为有日期的观测。数值评分与投放参数均为模拟预设。" if is_research else "以下数值均为模拟数据。") + "模型互动率以触达为分母。单人排序不等于预算约束下的组合推荐。")
    if filtered.empty:
        st.info("没有创作者满足当前筛选条件，请放宽平台、内容分类或指标范围。")
    else:
        visible = ["creator_id", "creator_name", "platform", "creator_category", "followers", "engagement_rate", "audience_match_score", "estimated_reach", "estimated_fee_usd", "content_quality_score", "total_score", "recommendation_reason", "data_type"]
        if is_research:
            visible += ["handle", "verification_status", "fit_rationale", "identity_data_type"]
        show_table(filtered[visible], hide_index=True, width="stretch", column_config={
            "followers": "粉丝数（有日期的观测）" if is_research else "粉丝数（模拟）",
            "engagement_rate": st.column_config.NumberColumn("模型互动率（比率）", format="%.3f"),
            "estimated_fee_usd": st.column_config.NumberColumn("模拟报价（美元）", format="$%.0f"),
            "total_score": st.column_config.NumberColumn("综合评分／100", format="%.2f"),
        })
        st.markdown("**排名靠前的创作者 · 规则生成的参考理由**")
        for _, row in filtered.head(3).iterrows():
            st.write(f"{row.creator_name} — {row.total_score:.2f}/100. {creator_reason_zh(row)}")

    with st.expander("评分方法与分项贡献"):
        st.write("综合评分＝各分项得分与目标权重乘积之和。各分项使用固定上限，筛选变化不会改变同一候选的分数。权重和上限是产品假设，不是行业基准。")
        st.json({zh_label(name): weight for name, weight in WEIGHTS[objective].items()})
        st.write("受众分＝预设匹配分；质量分＝预设内容质量分。受众调整触达＝预估触达×匹配分÷100（美国宠物科技场景的简化假设）。触达分＝min（调整触达÷100,000，1）×100；互动分＝min（互动率÷10%，1）×100。")
        st.write(f"效率分＝min（目标效果÷报价÷{EFFICIENCY_CAPS[objective]}，1）×100。品牌认知目标使用受众调整触达；互动目标使用调整触达×互动率；转化目标使用调整触达×CTR×CVR。转化数仅为演示计算值。")
        st.caption("CTR 和点击后购买 CVR 均为逐人固定假设；点击量不从互动量推导。合作费按一条模拟短视频计，不含样品、物流、税费或付费放大。质量分为预设，未通过 AI 审核视频。")
        details = ["creator_id"] + [f"{name}_{suffix}" for name in WEIGHTS[objective] for suffix in ("score", "contribution")] + ["total_score", "assumed_ctr", "assumed_click_to_purchase_cvr"]
        if not filtered.empty:
            show_table(filtered[details].round(4), hide_index=True, width="stretch")


result = optimize_portfolio(filtered, budget, objective, sample_usd, shipping_usd, max_creators)

metric_labels = {
    "budget_usd": "总预算（美元）", "spent_usd": "已使用预算（美元）",
    "remaining_usd": "剩余预算（美元）", "creator_count": "入选创作者数量",
    "raw_reach": "累计内容触达量（未去重）",
    "target_reach": "受众调整触达量（未去重）",
    "engagements": "预估互动量", "clicks": "预估点击量",
    "conversions": "预估转化量（非真实订单）",
    "cpm_usd": "每千次调整触达成本 CPM（美元）", "cpe_usd": "每次互动成本 CPE（美元）",
    "cpc_usd": "每次点击成本 CPC（美元）", "cpa_usd": "每次转化成本 CPA（美元）",
}

with overview_primary:
    st.subheader("当前推荐方案")
    render_metrics(result.metrics, {key: metric_labels[key] for key in ("spent_usd", "remaining_usd", "target_reach", "conversions")})
    st.caption(f"入选 {result.metrics['creator_count']} 位创作者 · 目标：{zh_label(objective)} · 预测触达未去重，转化不代表真实订单。")
    if budget > 0:
        st.progress(min(result.metrics['spent_usd'] / budget, 1.0), text=f"预算使用率 {result.metrics['spent_usd'] / budget:.1%}")
    if result.selected.empty:
        st.info("当前没有可推荐的组合。请检查侧栏预算及 KOL 数据库中的筛选条件。")
    else:
        st.markdown("**推荐名单**")
        show_table(result.selected[["creator_name", "platform", "execution_cost_usd", "total_score"]], hide_index=True, width="stretch")
    st.caption("主要风险：受众重叠、平台多样性及真实合作可用性未建模。累计触达未去重，预测转化不等同于订单或 ROI。")
    render_feature_entries()

with portfolio_tab:
    portfolio_main, portfolio_aside = detail_columns("portfolio")

with portfolio_main:
    st.subheader("预算与创作者组合")
    for message in result.messages:
        st.info(text_zh(message))
    render_metrics(result.metrics, metric_labels, columns_per_row=3)
    st.caption("粉丝数描述账号规模；单条预估触达描述一条短视频。组合触达是各创作者预估值相加，同一个人可能被重复计入。小数转化量表示数学期望。")
    st.write(f"优化器在预算内、最多 {max_creators} 人的约束下，最大化累计{zh_label(OUTCOME_COLUMNS[objective])}。单人评分按营销目标重算，供解释参考；优化器比较整个组合。")
    if not result.selected.empty:
        if is_research:
            st.warning("当前入选基于共用的模拟模板，不是对真实创作者表现的实证排名，也不表示已授权联系或预订。")
        show_table(result.selected[["creator_id", "creator_name", "platform", "creator_category", "estimated_fee_usd", "execution_cost_usd", "total_score", "target_reach", "projected_engagements", "projected_clicks", "projected_conversions", "selection_reason"]], hide_index=True, width="stretch")
        for _, selected_row in result.selected.iterrows():
            st.write(selection_reason_zh(selected_row))
        st.write(f"方案取舍：优先最大化模拟的{zh_label(objective)}效果，未加入平台多样性、受众重叠或评分质量约束。最高分创作者可能未入选，因为其他组合在预算内能产生更多模拟目标效果。未使用预算：${result.metrics['remaining_usd']:,.2f}。")
        omitted = result.candidates.loc[~result.candidates.creator_id.isin(result.selected.creator_id)].head(3)
        if not omitted.empty:
            st.caption("未入选组合的高分候选（不表示其单人报价都超出预算）：")
            show_table(omitted[["creator_id", "creator_name", "total_score", "execution_cost_usd", OUTCOME_COLUMNS[objective]]], hide_index=True)


campaign = dict(brand=brand, product=product, market=market, objective=objective, budget_usd=budget,
                sample_usd=sample_usd, shipping_usd=shipping_usd, max_creators=max_creators,
                platforms=", ".join(platforms), categories=", ".join(categories),
                min_followers=min_followers, min_engagement_pct=min_engagement, min_match=min_match,
                max_fee=max_fee, min_quality=min_quality, budget_only=budget_only,
                dataset=dataset, model_data_type="simulated")
current = make_snapshot(result, campaign, dataset_fingerprint)
baseline_key = "baseline_research" if is_research else "baseline"

with scenario_tab:
    scenario_main, scenario_aside = detail_columns("scenario")

with scenario_main:
    st.subheader("情景分析")
    left, right = st.columns(2)
    if left.button("保存当前方案为基准方案", key="save_baseline", type="primary", disabled=result.selected.empty):
        st.session_state[baseline_key] = current
        st.success("基准方案已保存。修改预算或营销目标，即可与当前方案比较。")
    if right.button("清除基准方案", key="clear_baseline"):
        st.session_state.pop(baseline_key, None)
    baseline = st.session_state.get(baseline_key)
    if baseline is None:
        st.info("请先保存一个可行组合为基准方案，再调整活动预算。")
    else:
        with st.expander("基准与当前方案参数"):
            st.json({"基准方案": campaign_zh(baseline["campaign"]), "当前方案": campaign_zh(campaign)})
        changes = [key for key in campaign if campaign[key] != baseline["campaign"].get(key)]
        if not changes:
            st.info("输入未变化，当前与基准是同一情景，可比较指标的变化均为 0。")
        else:
            st.write("变化的参数：" + "、".join(column_label(key) for key in changes))
            if "budget_usd" not in changes:
                st.info("预算未变化，结果差异来自其他参数调整。")
            if any(key != "budget_usd" for key in changes):
                st.warning("本次并非仅比较预算变化：其他活动参数或筛选条件也已调整。")
        try:
            comparison = compare_scenarios(baseline, current)
            comparison["metric"] = comparison.metric.map(metric_labels)
            show_table(comparison, hide_index=True, width="stretch")
            st.caption("绝对变化＝当前值－基准值。基准为 0 或单位成本不可计算时，不显示变化百分比。单位成本越低通常越好；效果增长仅是模型估算，不保证真实改善。")
            added = sorted(set(current["selected_ids"]) - set(baseline["selected_ids"]))
            removed = sorted(set(baseline["selected_ids"]) - set(current["selected_ids"]))
            st.write(f"新增创作者：{'、'.join(added) or '无'}；退出创作者：{'、'.join(removed) or '无'}。")
            if result.selected.empty:
                st.warning("当前情景无可行组合。零投放活动和“不适用”的单位成本不代表相对基准的效率改善。")
        except ValueError as exc:
            st.warning(text_zh(str(exc)))


with report_tab:
    report_main, report_aside = detail_columns("report")

with report_main:
    st.subheader("方案报告")
    st.caption("导出与当前预算、目标和筛选结果同步。所有预测来自程序计算。")
    render_metrics(result.metrics, {key: metric_labels[key] for key in ("budget_usd", "spent_usd", "remaining_usd", "creator_count")}, columns_per_row=2)
    with st.expander("预测公式与规划假设"):
        st.write("原始内容触达＝模拟单条触达。受众调整触达＝原始触达×受众匹配分÷100；这是美国宠物科技场景的简化假设，不是实测地域分布。组合指标逐人相加。")
        st.write("互动量＝受众调整触达×模型互动率。点击量＝受众调整触达×CTR。转化量＝点击量×CVR。点击量不从互动量推导；所有模型率均为 CSV 中的模拟比率。")
        st.write("单人执行成本＝合作费＋样品＋物流。已使用预算＝执行成本合计；剩余预算＝总预算－已使用预算。CPM＝支出÷受众调整触达×1,000；CPE＝支出÷互动量；CPC＝支出÷点击量；CPA＝支出÷转化量。分母为 0 时显示“不适用”。")
        st.write("算法采用精确的 0/1 背包动态规划，以整数美分计费，最多选择 6 人；每人仅能入选一次。模拟效果相同则优先低成本，再按固定编号顺序决胜。筛选不改变单人分数；情景比较前核对数据及模型版本。")
        st.warning(DISCLAIMER_ZH)

    with st.expander("术语说明"):
        st.write("基于透明假设，筛选创作者并比较营销活动（Campaign）方案。KOL 指关键意见领袖／内容创作者；默认案例为 PETKIT，品牌及产品名称可修改。点击率（CTR）、点击后购买转化率（CVR）均使用明确标注的模拟假设。")

with database_aside:
    render_campaign_context(brand, market, zh_label(objective))
    st.divider()
    st.markdown("**资料与核验**")
    if is_research:
        st.caption(f"研究身份 {len(research)} 个；模型参数完整 {len(data)} 个。")
        st.info("公开资料仅部分核实。来源、日期、缺失字段和资格审计可在主卡展开。")
    else:
        st.info("当前使用固定模拟身份与模拟投放参数，仅用于演示。")
    st.caption("未知观测保持缺失，不补为 0；第三方估计不代表创作者后台数据。")

with portfolio_aside:
    render_campaign_context(brand, market, zh_label(objective))
    st.divider()
    st.markdown("**规划边界**")
    st.caption(f"最多选择 {max_creators} 人 · 每人一条模拟短视频。")
    st.info("优化器比较组合的整体目标效果。最高单人评分不保证入选。")
    st.caption("报价、触达及模型率均为模拟假设；合作授权、受众重叠与平台多样性未建模。")

with scenario_aside:
    render_campaign_context(brand, market, zh_label(objective))
    st.divider()
    st.markdown("**比较前检查**")
    st.caption("基准状态：" + ("已保存（当前数据集）" if baseline is not None else "尚未保存"))
    st.info("保存基准后，在左侧调整预算或目标。基准保留原输入，当前方案自动重算。")
    st.caption("差异来自模型假设，不代表真实效果改善；数据集的基准分别保存。")

with report_aside:
    render_campaign_context(brand, market, zh_label(objective))
    st.divider()
    st.subheader("导出当前组合")
    if result.selected.empty:
        st.info("存在可行组合后才能下载 CSV。")
    else:
        st.download_button("下载当前组合 CSV", data=export_portfolio_csv(result, campaign),
                           file_name=f"{'research_identity_simulated_model' if is_research else 'simulated_kol'}_portfolio_{objective.lower().replace(' ', '_')}_{budget}usd.csv",
                           mime="text/csv", key="download_portfolio", type="primary")
        st.caption("采用带 BOM 的 UTF-8 编码，便于 Excel 打开。每行一位创作者，含活动参数、预测及重复的组合总额；不要将 portfolio_* 总额列再次逐行相加。")


st.divider()
st.caption("独立作品集项目，与 PETKIT 无隶属关系，也未获其背书。" + DISCLAIMER_ZH)
