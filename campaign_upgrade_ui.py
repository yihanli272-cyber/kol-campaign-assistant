"""Incremental panels for 第三方报告 research and campaign decisions."""
import uuid
import pandas as pd
import streamlit as st
from campaign_upgrade import load_supplement, score_v2, force_include, compare_results, effect_scenario, decision_details
from sprint_decision import run_plan, safe_csv
from sprint_research import SCORE_WEIGHTS
from ui_layout import value_chart, outcome_charts, comparison_charts, portfolio_change_charts

def render_upgrade(tables, screen, model, result, objective, budget, mode, database, recommendation, scenarios, report, campaign=None, supplement_path=None, priority_area=None):
    from sprint_ui import table, LABELS, research_area, creator_cards, decision_summary
    LABELS.update({'hicreator_match_rate':'第三方报告匹配度（比率，非转化概率）','hicreator_followers':'第三方报告粉丝数','hicreator_avg_views':'第三方报告平均播放量','hicreator_median_views':'第三方报告中位播放量','hicreator_engagement_rate':'第三方报告互动率','content_tags':'第三方报告内容标签','representative_posts':'代表性原帖（未知待补充）','collected_at':'导出采集日期','match_source':'匹配度来源','screenshot_received_at':'截图收到日期（非采集日期）','screenshot_metric_basis':'截图统计口径','decision_category':'决策类别','simulated_cost':'模拟成本','simulated_objective_contribution':'模拟目标贡献','verified_posts':'已核验支持原帖','missing_reasons':'缺失原因','score_version':'评分版本','v2_weights':'当前目标权重'})
    supplement=load_supplement(tables['accounts'], **({'path': supplement_path} if supplement_path is not None else {}))
    scores=score_v2(tables,screen,objective,model,supplement,fit_keyword_groups=(campaign or {}).get('fit_keyword_groups'))
    details=decision_details(tables,supplement,result,objective)
    with database:
        with research_area('外部研究来源与完整补充记录'):
            st.subheader('第三方报告 外部研究依据 · 独立补充表')
            st.caption('原始来源与采集日期用于追溯；匹配度不等于产品适配或转化概率。本工具提供目标匹配、组合优化与预算决策。')
            table(supplement)
            st.write('内置PETKIT搜索截图案例（不代表新Campaign适配结论）：KOL-001与KOL-002均为100%匹配，但公开播放和互动不同，不能仅按匹配度作投放决定。截图时间未知；2026-10-31为收到截图日期。缩略图没有原帖URL或日期，未作为核验证据。')
            ids=st.multiselect('第三方报告 双人对比',supplement.creator_id.tolist(),default=[cid for cid in ['KOL-001','KOL-002'] if cid in set(supplement.creator_id)],max_selections=2,key='hc_compare')
            if len(ids)==2:
                with st.expander('第三方报告双人图表 · 第三方指标与五维评分'):
                    comparison_charts(tables['accounts'],scores,ids,['产品内容适配度','内容表现','互动表现','商业适配度','模拟预算效率'])
                table(supplement.loc[supplement.creator_id.isin(ids)])
                table(model.loc[model.creator_id.isin(ids)])
                st.caption('上表为第三方观察，下表为当前范围内独立模拟参数；不在模拟池的账号不自动补参数。')
    with (priority_area if priority_area is not None else recommendation):
        st.subheader('Priority Creators · 决策卡片')
        creator_cards(tables,screen,model,supplement,details)
        st.caption('卡片展示重点研究对象；部分账号可能未进入当前平台或模拟参数范围，不代表内容质量差。正式投放资格仍为0时不构成正式推荐。')
        with research_area('完整v2评分与证据覆盖'):
            st.subheader('Campaign评分 v2 · 保留v1评分与证据覆盖')
            st.caption('v2将商业适配与证据覆盖分开；没有真实合作形式、报价及目标市场证据时，商业适配保持未知，不用模拟报价补分。平均/中位播放及近期帖子分别展示，不混成未经验证的广告效果。')
            table(scores)
        st.subheader('逐人决策依据 · 真实证据与模拟贡献')
        with st.expander('入选与淘汰类别 · 决策概览'):
            summary=details.groupby('decision_category').size().rename('人数').reset_index()
            value_chart(summary,'decision_category','人数','决策类别分布（当前计算范围）','人数',horizontal=True)
            st.caption('颜色只表示决策类别，不代表证据已核验；具体理由与来源见明细。')
        decision_summary(details, result)
    scenario_exports=[]
    with scenarios:
        st.subheader('交互预算比较 · $3,000 / $5,000 / $7,000')
        st.caption('本区域预算比较、效果原基准、强制加入沿用侧栏当前效果等级；效果控件仅覆盖效果对照方案。上方独立What-if的修改不自动应用于本区域。')
        budgets=st.multiselect('预算比较范围',[3000,5000,7000],default=[3000,5000,7000],key='upgrade_budgets')
        base=run_plan(model,5000,objective)
        baseids=set(base.selected.get('creator_id',[]))
        rows=[]
        allocations=[]
        for b in budgets:
            p=run_plan(model,b,objective)
            ids=set(p.selected.get('creator_id',[]))
            for r in p.selected.itertuples():
                allocations.append(dict(预算=b,达人=r.creator_id,模拟支出USD=r.execution_cost_usd))
            rows.append(dict(情景类型='预算',预算=b,入选=','.join(sorted(ids)),新增=','.join(sorted(ids-baseids)),退出=','.join(sorted(baseids-ids)),预算使用率=p.metrics['spent_usd']/b,**p.metrics))
        with st.expander('预算效果与分配图 · Simulation'):
            chart_rows=pd.DataFrame(rows)
            outcome_charts(chart_rows,'预算','不同预算的预测效果')
            value_chart(pd.DataFrame(allocations),'预算','模拟支出USD','达人预算分配（堆叠）','USD',group='达人',stack=True)
            value_chart(chart_rows,'预算','target_reach','预算与模拟触达关系','触达人次（未去重）',line=True)
            st.caption('费用来自各预算实际入选者，效果来自现有优化器；未使用预算不会分配给任何达人。')
        table(pd.DataFrame(rows))
        scenario_exports.extend(rows)
        st.subheader('效果假设 · 当前预算及营销目标')
        reach=st.number_input('模拟预计触达倍率',min_value=0.,max_value=10.,value=1.,step=.1,key='effect_reach')
        er=st.number_input('模拟模型互动率（%）',min_value=0.,max_value=100.,value=5.,step=.5,key='effect_er')/100
        ctr=st.number_input('效果情景 CTR（%）',min_value=0.,max_value=100.,value=1.,step=.1,key='effect_ctr')/100
        cvr=st.number_input('效果情景 CVR（%）',min_value=0.,max_value=100.,value=2.,step=.1,key='effect_cvr')/100
        baseline,fixed,optimized=effect_scenario(model,budget,objective,reach,er,ctr,cvr)
        frames=[]
        for label,p in [('原基准',baseline),('固定组合重算',fixed),('重新优化',optimized)]:
            ids=set(p.selected.get('creator_id',[])); original=set(baseline.selected.get('creator_id',[]))
            frames.append(dict(情景类型='效果假设',reach_multiplier=1. if label=='原基准' else reach,assumed_er=None if label=='原基准' else er,assumed_ctr=None if label=='原基准' else ctr,assumed_cvr=None if label=='原基准' else cvr,parameter_basis='基准逐人参数见baseline_parameters' if label=='原基准' else '当前效果控件覆盖参数',baseline_parameters=model[['creator_id','estimated_reach','engagement_rate','assumed_ctr','assumed_click_to_purchase_cvr']].to_json(orient='records'),计算=label,入选=','.join(sorted(ids)),新增=','.join(sorted(ids-original)),退出=','.join(sorted(original-ids)),**p.metrics))
        with st.expander('固定组合与重新优化 · Simulation效果对比'):
            outcome_charts(pd.DataFrame(frames),'计算','同一效果假设下的两种计算')
        table(pd.DataFrame(frames)); scenario_exports.extend(frames)
        st.caption('共同倍率可能保持名单不变；互动率统一覆盖可能改变互动目标排序，变化来自输入计算。')
        if st.button('保存此效果情景独立快照',key='effect_save'):
            snapshot=dict(campaign=campaign, snapshot_id=uuid.uuid4().hex,mode=mode,objective=objective,budget=budget,reach_multiplier=reach,engagement_rate=er,ctr=ctr,cvr=cvr,model_csv=model.to_csv(index=False),results=frames)
            st.session_state.setdefault('campaign_v2_snapshots',[]).append(snapshot)
        snapshots=st.session_state.get('campaign_v2_snapshots',[])
        st.caption(f'本会话独立快照：{len(snapshots)}（保留当时参数和候选模型，重算不覆盖；重启后请使用导出文件）')
        for snap in snapshots:
            with st.expander('快照 '+snap['snapshot_id'][:8]):
                st.json({k:v for k,v in snap.items() if k not in ['model_csv','results']})
                table(pd.DataFrame(snap['results']))
        st.subheader('强制加入一位未入选达人 · 保持当前预算与目标')
        base=run_plan(model,budget,objective)
        omitted=model.loc[~model.creator_id.isin(base.selected.get('creator_id',[]))]
        if omitted.empty:
            st.info('当前没有可强制加入的未入选计算候选；不能绕过正式资格。')
        else:
            forced_id=st.selectbox('强制加入未入选候选',omitted.creator_id.tolist(),key='forced_creator')
            try:
                original,forced=force_include(model,forced_id,budget,objective)
                old=set(original.selected.creator_id); new=set(forced.selected.creator_id)
                st.write('退出：'+(','.join(sorted(old-new)) or '无')+'；进入：'+(','.join(sorted(new-old)) or '无'))
                portfolio_change_charts(original,forced,'强制加入前后')
                comparison=compare_results(original,forced)
                table(comparison)
                metric={'Brand Awareness':'target_reach','Engagement':'engagements','Conversion':'conversions'}[objective]
                loss=original.metrics[metric]-forced.metrics[metric]
                st.write(f'相同预算上限 ${budget:,.0f}；实际支出变化 ${forced.metrics["spent_usd"]-original.metrics["spent_usd"]:,.2f}；强制加入后的模拟目标损失 {loss:,.4f}。零损失表示同等目标效果的替代组合；正损失支持原组合在当前假设下更优，不能证明真实营销优劣。')
                table(forced.selected[[c for c in ['creator_id','platform','estimated_fee_usd','target_reach','projected_engagements','projected_clicks','projected_conversions'] if c in forced.selected]])
                with st.expander('强制加入组合 · 完整模拟字段与来源'):
                    table(forced.selected)
                st.download_button('导出强制加入计算差额',safe_csv(comparison.assign(forced_creator=forced_id,objective=objective,planning_mode=mode,campaign_config=str(campaign))),file_name='forced_comparison.csv')
            except ValueError as exc:
                st.info(str(exc))
    with report:
        st.caption('新版导出均附当前Campaign配置；原匹配度仍为原搜索条件下第三方报告。')
        st.download_button('导出第三方报告补充资料与核验来源',safe_csv(supplement.assign(campaign_config=str(campaign))),file_name='third_party_supplement.csv')
        st.download_button('导出Campaign v2评分',safe_csv(scores.assign(campaign_config=str(campaign))),file_name='campaign_scores_v2.csv')
        st.download_button('导出逐人决策详细依据',safe_csv(details.assign(planning_mode=mode,campaign_config=str(campaign))),file_name='campaign_decisions_v2.csv')
        st.download_button('导出交互情景结果与模拟参数',safe_csv(pd.DataFrame(scenario_exports).assign(planning_mode=mode,objective=objective,campaign_config=str(campaign))),file_name='interactive_scenarios_v2.csv')
        if snapshots:
            import json
            st.download_button('导出独立快照（含候选与参数）',json.dumps(snapshots,ensure_ascii=False,indent=2),file_name='campaign_snapshots.json')
