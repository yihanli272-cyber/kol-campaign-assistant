"""Presentation-only showcase. Forecasts/search delegate to existing business functions."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from sprint_decision import adapt_model, run_plan, safe_csv
from campaign_upgrade import force_include, compare_results, load_supplement
from portfolio import OUTCOME_COLUMNS, PortfolioResult, summarize
from ui_layout import value_chart, outcome_charts

CONFIG = Path(__file__).with_name('demo_simulation.json')
METRICS = {'target_reach':'预计触达', 'engagements':'预计互动', 'clicks':'预计点击', 'conversions':'预计转化'}
PUBLIC_COLUMNS = ['creator_id','platform','handle','estimated_fee_usd','estimated_reach','engagement_rate',
                  'assumed_ctr','assumed_click_to_purchase_cvr','target_reach','projected_engagements',
                  'projected_clicks','projected_conversions']


def demo_model(tables, screen):
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    model = adapt_model(tables, screen, sandbox=True)
    model = model.loc[model.creator_id.isin(config['creators'])].copy()
    for column,value in config['model_presets'].items():
        model[column] = value
    for cid, p in config['creators'].items():
        for column, key in [('estimated_fee_usd','fee'), ('estimated_reach','reach'), ('engagement_rate','er'),
                            ('assumed_ctr','ctr'), ('assumed_click_to_purchase_cvr','cvr')]:
            model.loc[model.creator_id.eq(cid),column] = p[key]
        # Keep the existing model-schema version; track the independent input version separately.
        model.loc[model.creator_id.eq(cid),'source_assumption_version'] = config['version']
    return model, config


def public_export(result, config, objective):
    frame = result.candidates[[c for c in PUBLIC_COLUMNS if c in result.candidates]].copy()
    frame['selected'] = frame.creator_id.isin(result.selected.get('creator_id', [])) if 'creator_id' in frame else pd.Series(dtype=bool)
    frame['objective'] = objective
    frame['simulation_version'] = config['version']
    frame['simulation_notice'] = config['notice']
    for key, val in result.metrics.items():
        if val is not None:
            frame['portfolio_' + key] = val
    return frame


def scenario_results(model, budget, objective):
    """Independent results, same existing optimizer and fixed-combination summarizer."""
    baseline = run_plan(model,budget,objective)
    budgets = [(f'${b:,}',run_plan(model,b,objective)) for b in (3000,5000,7000)]
    objectives = [(o,run_plan(model,budget,o)) for o in OUTCOME_COLUMNS]
    effects = []
    for label, factor in [('保守',0.7),('基准',1.0),('乐观',1.3)]:
        changed = model.copy(deep=True)
        for field in ['estimated_reach','engagement_rate','assumed_ctr','assumed_click_to_purchase_cvr']:
            changed[field] = model[field] * factor
        changed['estimated_reach'] = changed['estimated_reach'].round()
        optimized = run_plan(changed,budget,objective)
        fixed = optimized.candidates.loc[optimized.candidates.creator_id.isin(baseline.selected.get('creator_id', []))].copy() if not optimized.candidates.empty else pd.DataFrame()
        effects.append((label,factor,PortfolioResult(fixed,optimized.candidates,summarize(fixed,budget),[]),optimized))
    return baseline,budgets,objectives,effects


def selection_text(result, handles):
    return ' · '.join('@' + handles[c] for c in result.selected.get('creator_id', [])) or '当前预算未分配'


def discovery_records(accounts, supplement_path=None):
    """Read-only public projection; join by stable ID and platform, never by name."""
    supplement=load_supplement(accounts, **({'path':supplement_path} if supplement_path is not None else {}))
    fields=['creator_id','platform','handle','creator_name','profile_url','reported_followers',
            'reported_mean_views','reported_median_views','reported_mean_engagement_rate']
    records=accounts[fields].copy(deep=True)
    matches=supplement.set_index(['creator_id','platform'])['hicreator_match_rate']
    # Map only the optional metric; a merge would coerce original string dtypes.
    records['match_rate']=[matches.loc[(row.creator_id,row.platform)] for row in records.itertuples(index=False)]
    return records


def filter_discovery(records, platform='全部平台', query=''):
    result=records.copy(deep=True)
    if platform!='全部平台':
        result=result.loc[result.platform.eq(platform)]
    query=query.strip().lstrip('@')
    if query:
        searchable=result[['creator_id','handle','creator_name']].fillna('').astype(str).agg(' '.join,axis=1)
        result=result.loc[searchable.str.contains(query,case=False,regex=False)]
    return result.reset_index(drop=True)


def render_discovery(records):
    st.subheader('Creator Discovery · 完整达人库')
    st.caption(f'共 {len(records)} 条独立平台账号记录；浏览与搜索不会改变 Campaign Shortlist 或预算计算范围。')
    for col,platform in zip(st.columns(3),['Instagram','TikTok','YouTube']):
        col.metric(platform,int(records.platform.eq(platform).sum()))
    platform=st.selectbox('Discovery 平台',['全部平台','Instagram','TikTok','YouTube'],key='discovery_platform')
    query=st.text_input('搜索账号、名称或编号',key='discovery_query',placeholder='例如 @ponyoandluna 或 KOL-041')
    filtered=filter_discovery(records,platform,query)
    if filtered.empty:
        st.info('没有符合当前条件的账号，请调整平台或搜索关键词。')
        return
    pages=list(range(1,(len(filtered)+5)//6+1))
    if st.session_state.get('discovery_page',1) not in pages:
        st.session_state['discovery_page']=1
    page=st.selectbox('Discovery 页码',pages,key='discovery_page')
    start=(page-1)*6
    st.caption(f'符合条件 {len(filtered)} 条 · 第 {page} / {len(pages)} 页 · 显示 {start+1}–{min(start+6,len(filtered))} 条')
    for i,row in enumerate(filtered.iloc[start:start+6].itertuples(index=False)):
        if i%2==0:
            columns=st.columns(2)
        with columns[i%2],st.container(border=True):
            st.markdown(f'### {row.platform} · @{row.handle}')
            st.caption(row.creator_id)
            st.link_button('查看达人主页',row.profile_url)
            fields=[('reported_followers','粉丝数'),('reported_mean_views','历史平均播放'),
                    ('reported_median_views','历史中位播放'),('reported_mean_engagement_rate','历史互动率'),('match_rate','匹配度')]
            available=[(field,label) for field,label in fields if pd.notna(getattr(row,field))]
            for offset in range(0,len(available),2):
                for col,(field,label) in zip(st.columns(2),available[offset:offset+2]):
                    value=float(getattr(row,field))
                    col.metric(label,f'{value:.2%}' if field.endswith('rate') else f'{value:,.0f}')
    st.caption('历史指标用于资料比较；已有匹配度仅对应原检索任务，不等于当前产品适配或转化概率。')


def render_showcase(tables, screen, campaign, budget, objective, platforms, supplement_path=None):
    model, config = demo_model(tables,screen)
    model = model.loc[model.platform.isin(platforms)].copy()
    result,budgets,objectives,effects = scenario_results(model,budget,objective)
    accounts = tables['accounts'].set_index('creator_id')
    handles = accounts.handle.to_dict()
    st.caption(config['notice'])
    st.caption('历史账号指标仅作资料参考；Simulation 规划参数独立配置。内容方向为资料线索，不代表已观看原帖或已建立合作。')
    overview,discovery,shortlist,decision,scenario,whatif = st.tabs(['Campaign Overview','Creator Discovery','Creator Shortlist','Creator Decision','Scenario Simulator','What-if Analysis'])
    with discovery:
        render_discovery(discovery_records(tables['accounts'],supplement_path))
    with overview:
        for col,label,value in zip(st.columns(3),['Campaign Budget · USD','Selected Creators','Estimated Reach · Simulation'],
                                   [f'${budget:,.0f}',str(len(result.selected)),f"{result.metrics['target_reach']:,.0f}"]):
            col.metric(label,value)
        for col,key in zip(st.columns(3),['engagements','clicks','conversions']):
            col.metric(METRICS[key]+' · Simulation',f'{result.metrics[key]:,.1f}')
        used = result.metrics['spent_usd']/budget if budget else 0
        st.progress(min(used,1.),text=f"Simulation · 已分配 ${result.metrics['spent_usd']:,.0f} · 使用率 {used:.1%}")
        st.write('当前组合：'+selection_text(result,handles))
        if not result.selected.empty:
            distribution=result.selected.groupby('platform').size().rename('人数').reset_index()
            st.markdown('**入选组合 · 平台分布**')
            st.vega_lite_chart(distribution,{'height':240,'padding':{'top':16,'bottom':16,'left':16,'right':16},'mark':{'type':'arc','innerRadius':65},'encoding':{'theta':{'field':'人数','type':'quantitative'},'color':{'field':'platform','type':'nominal','title':'平台','legend':{'orient':'bottom'},'scale':{'range':['#207968','#4e79a7','#d18a36']}},'tooltip':[{'field':'platform'},{'field':'人数'}]}},width='stretch')
            outcome_charts(pd.DataFrame([dict(方案='当前组合',**result.metrics)]),'方案','Campaign效果概览')
        st.caption('组合在预算与最多6人约束下最大化当前目标；触达为人次相加，未跨平台去重。')
    with shortlist:
        st.subheader('六位重点候选 · 跨平台 Shortlist')
        selected_compare=st.multiselect('选择两位候选比较历史指标',list(config['creators']),default=['KOL-014','KOL-006'],max_selections=2,format_func=lambda x:'@'+handles[x])
        if len(selected_compare)==2:
            compare=accounts.loc[selected_compare].reset_index().copy()
            compare['账号']=compare.handle
            with st.expander('Creator Comparison · 历史指标',expanded=False):
                for field,label,unit in [('reported_followers','粉丝数','人'),('reported_mean_views','历史平均播放','次'),('reported_median_views','历史中位播放','次'),('reported_mean_engagement_rate','历史互动率','比率')]:
                    value_chart(compare,'账号',field,label,unit,horizontal=True)
        for i,cid in enumerate(config['creators']):
            a=accounts.loc[cid]; p=config['creators'][cid]
            if i % 2 == 0:
                card_columns = st.columns(2)
            with card_columns[i % 2], st.container(border=True):
                st.markdown(f"### {a.platform} · @{a.handle}")
                st.link_button('查看账号主页',a.profile_url)
                cols=st.columns(4)
                for col,field,label in zip(cols,['reported_followers','reported_mean_views','reported_median_views','reported_mean_engagement_rate'],['粉丝数','历史平均播放','历史中位播放','历史互动率']):
                    v=a[field]
                    if pd.notna(v) and str(v).strip():
                        col.metric(label,f'{float(v):.2%}' if 'rate' in field else f'{float(v):,.0f}')
                categories=screen.set_index('creator_id').loc[cid,'categories']
                if categories and categories!='Unknown':
                    st.write('内容方向（资料线索）：'+categories)
                if pd.notna(a.reported_position) and str(a.reported_position).strip():
                    st.write('产品场景线索：'+str(a.reported_position))
                st.caption('Simulation · '+p['format'])
                st.write(f"模拟报价 **${p['fee']:,.0f}** · 预计触达 **{p['reach']:,}** · 互动率 **{p['er']:.1%}** · CTR **{p['ctr']:.1%}** · CVR **{p['cvr']:.1%}**")
        st.download_button('下载 Simulation 参数',CONFIG.read_bytes(),'simulation_parameters.json','application/json')
    with decision:
        st.subheader('预算与目标驱动的组合决策 · Simulation')
        target=OUTCOME_COLUMNS[objective]
        if not result.candidates.empty:
            chart=result.candidates.copy(); chart['账号']=chart.creator_id.map(handles); chart['组合状态']=chart.creator_id.isin(result.selected.creator_id).map({True:'入选',False:'备选'})
            value_chart(chart,'账号',target,'目标贡献 · '+objective,'模拟目标贡献',group='组合状态',horizontal=True)
            for r in result.candidates.itertuples():
                selected=r.creator_id in set(result.selected.creator_id)
                with st.container(border=True):
                    st.markdown(f"**@{handles[r.creator_id]} · {'入选模拟组合' if selected else '组合备选'}**")
                    st.write(f"模拟成本 ${r.execution_cost_usd:,.0f} · 目标贡献 {getattr(r,target):,.1f}")
                    st.caption('在当前约束下参与最优整体组合。' if selected else '单人模拟成本超过当前预算。' if r.execution_cost_usd>budget else '当前其他可行组合的整体目标贡献更高或等优；可在 What-if 检查强制加入的机会成本。')
        st.download_button('下载当前决策 CSV',safe_csv(public_export(result,config,objective)),'campaign_decision_simulation.csv','text/csv')
        st.download_button('下载 Campaign 配置',json.dumps({**campaign,'budget':budget,'objective':objective},ensure_ascii=False,indent=2).encode('utf-8'),'campaign_config.json','application/json')
    with scenario:
        scenario_rows=[]
        a,b,c=st.tabs(['Budget Scenario','Marketing Objective','Performance Assumptions'])
        for area,plans in [(a,budgets),(b,objectives)]:
            with area:
                rows=pd.DataFrame([dict(情景=label,**p.metrics) for label,p in plans])
                scenario_rows.extend([dict(情景=label,类别='预算' if area is a else '营销目标',组合=';'.join(p.selected.get('creator_id', [])),**p.metrics) for label,p in plans])
                outcome_charts(rows,'情景','实际优化结果 · Simulation')
                allocations=[]
                for label,p in plans:
                    with st.container(border=True):
                        st.write(f'**{label}** · '+selection_text(p,handles))
                        st.caption(f"支出 ${p.metrics['spent_usd']:,.0f} · 使用率 {p.metrics['spent_usd']/p.metrics['budget_usd']:.1%}" if p.metrics['budget_usd'] else '预算 $0')
                    for r in p.selected.itertuples():
                        allocations.append(dict(情景=label,账号=handles[r.creator_id],支出=r.execution_cost_usd))
                value_chart(pd.DataFrame(allocations),'情景','支出','组合预算分配 · Simulation','USD',group='账号',stack=True)
                st.caption('只改变对应情景参数；组合不变表示当前最优解保持稳定。')
        with c:
            st.caption('Simulation · 保守 / 基准 / 乐观分别将独立配置中的触达、互动率、CTR、CVR乘以0.7 / 1.0 / 1.3。')
            rows=[]; rates=[]
            for label,factor,fixed,opt in effects:
                for name,p in [('固定组合重算',fixed),('重新优化',opt)]:
                    rows.append(dict(情景=label,计算方式=name,**p.metrics))
                    scenario_rows.append(dict(情景=label,类别=name,组合=';'.join(p.selected.get('creator_id', [])),**p.metrics))
                for r in model.itertuples():
                    rates.append(dict(情景=label,账号=handles[r.creator_id],CTR=r.assumed_ctr*factor*100,CVR=r.assumed_click_to_purchase_cvr*factor*100))
                st.write(f'**{label} · 重新优化：** '+selection_text(opt,handles))
            for col,metric in zip(st.columns(2),['clicks','conversions']):
                with col:value_chart(pd.DataFrame(rows),'情景',metric,METRICS[metric]+' · Simulation','次数',group='计算方式',line=True)
            for col,metric in zip(st.columns(2),['CTR','CVR']):
                with col:value_chart(pd.DataFrame(rates),'情景',metric,metric+' · Simulation','%',group='账号',line=True)
            st.caption('固定组合保留当前基准入选名单；重新优化使用同一组新假设再次搜索预算组合。')
        export=pd.DataFrame(scenario_rows)
        export['simulation_notice']=config['notice']
        export['simulation_version']=config['version']
        st.download_button('下载情景结果 CSV',safe_csv(export),'scenario_simulation.csv','text/csv')
    with whatif:
        choices=[cid for cid in model.creator_id if cid not in set(result.selected.get('creator_id', []))]
        if choices:
            cid=st.selectbox('选择强制加入的备选达人',choices,format_func=lambda x:'@'+handles[x])
            try:
                before,after=force_include(model,cid,budget,objective)
            except ValueError:
                st.info('该候选的模拟成本超过当前预算；请先提高预算。')
            else:
                left,right=st.columns(2)
                left.write('**原始组合** · '+selection_text(before,handles)); right.write('**强制加入后** · '+selection_text(after,handles))
                removed=set(before.selected.creator_id)-set(after.selected.creator_id)
                st.write('被替换：'+(' · '.join('@'+handles[x] for x in sorted(removed)) or '无'))
                delta=compare_results(before,after).set_index('metric')
                for col,key in zip(st.columns(3),['spent_usd','target_reach','conversions']):
                    col.metric('模拟支出 USD' if key=='spent_usd' else METRICS[key],f'{after.metrics[key]:,.1f}',f"{delta.loc[key,'delta']:+,.1f}",delta_color='off')
                for key in ['engagements','clicks']:
                    st.write(f"{METRICS[key]}变化：{delta.loc[key,'delta']:+,.1f} · Simulation")
                outcome_charts(pd.DataFrame([dict(组合='原组合',**before.metrics),dict(组合='强制加入',**after.metrics)]),'组合','前后组合对比')
                difference=after.metrics[{'Brand Awareness':'target_reach','Engagement':'engagements','Conversion':'conversions'}[objective]]-before.metrics[{'Brand Awareness':'target_reach','Engagement':'engagements','Conversion':'conversions'}[objective]]
                st.caption(f'强制预留该候选成本后，现有优化器重算剩余预算。当前目标贡献变化 {difference:+,.2f}；差额为零时属于等优组合，不能据此声称效果更好。')
        else:
            st.caption('当前计算范围的候选已全部入选；可降低预算后比较组合取舍。')
