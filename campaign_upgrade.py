"""HiCreator external observations and computed campaign counterfactuals, version 2."""
from pathlib import Path
import pandas as pd
from creator_registry import REGISTRY_DIR
from sprint_research import score_registry, number, text
from sprint_decision import run_plan
from portfolio import optimize_portfolio, summarize, PortfolioResult, OUTCOME_COLUMNS

SUPPLEMENT = REGISTRY_DIR / 'hicreator_supplement.csv'

def load_supplement(accounts, path=SUPPLEMENT):
    if not Path(path).exists():
        data = accounts[['creator_id','platform']].copy()
        mapping = {'hicreator_followers':'reported_followers','hicreator_avg_views':'reported_mean_views','hicreator_median_views':'reported_median_views','hicreator_engagement_rate':'reported_mean_engagement_rate','evidence_source':'data_source','collected_at':'export_date'}
        for target, source in mapping.items():
            data[target] = accounts[source].values
        for field in ['hicreator_match_rate','content_tags','representative_posts','post_date','post_views','post_engagement']:
            data[field] = None
        data['evidence_status'] = 'third_party_unverified'
        return data
    data = pd.read_csv(path, dtype={'creator_id': 'string'}, keep_default_na=True)
    if 'hicreator_match_rate' not in data:
        data['hicreator_match_rate'] = None
    if data.creator_id.duplicated().any() or set(data.creator_id) != set(accounts.creator_id):
        raise ValueError('HiCreator补充表必须与52条内部ID一一对应。')
    platforms = accounts.set_index('creator_id').platform
    if not data.apply(lambda r: r.platform == platforms[r.creator_id], axis=1).all():
        raise ValueError('补充表平台不匹配；不得按同名合并。')
    for field in ['hicreator_match_rate', 'hicreator_engagement_rate']:
        values = pd.to_numeric(data[field], errors='raise')
        if not values.dropna().between(0, 1).all():
            raise ValueError('HiCreator比率应为0–1。')
    return data

def score_v2(tables, screen, objective, model, supplement, fit_keyword_groups=None):
    old = score_registry(tables, screen, objective, model, fit_keyword_groups=fit_keyword_groups)
    result = old.rename(columns={'数据证据可信度': '证据覆盖分（辅助）'}).copy()
    result['商业适配度'] = None
    result['商业适配依据'] = 'Unknown：真实报价、合作形式、目标受众或市场证据未齐；模拟报价不能证明商业适配'
    result['score_version'] = 'campaign-v2'
    dims = ['产品内容适配度', '内容表现', '互动表现', '商业适配度', '模拟预算效率']
    weights = {'Brand Awareness': [.25,.35,.10,.10,.20], 'Engagement': [.25,.10,.35,.10,.20], 'Conversion': [.30,.10,.10,.20,.30]}[objective]
    source=supplement.set_index('creator_id')
    for index,row in result.iterrows():
        observed=source.loc[row.creator_id]
        avg=number(observed.hicreator_avg_views); median=number(observed.hicreator_median_views)
        result.loc[index,'内容表现'] = min((avg+median)/2/100000*100,100) if avg is not None and median is not None else None
    result['performance_basis'] = 'v2：平均播放与中位播放等权平均÷100000×100，封顶100；任一缺失不补分；近期帖子不足，近期表现未知；非投放触达'
    result['score_completeness'] = result[dims].notna().sum(axis=1)/5
    result['known_contribution'] = result.apply(lambda r: sum(float(r[d])*w for d,w in zip(dims,weights) if pd.notna(r[d])),axis=1)
    result['total_score'] = None
    result['missing_reasons'] = result.apply(lambda r: '；'.join(d + '待补充' for d in dims if pd.isna(r[d])), axis=1)
    result['v2_weights'] = str(dict(zip(dims,weights)))
    return result.merge(supplement, on=['creator_id','platform'], how='left', validate='one_to_one')

def force_include(model, creator_id, budget=5000, objective='Brand Awareness'):
    baseline = run_plan(model, budget, objective)
    if creator_id not in set(baseline.candidates.get('creator_id', [])):
        raise ValueError('该达人不在当前合格计算池内；不能强制绕过资格或补齐未知假设。')
    forced = baseline.candidates.loc[baseline.candidates.creator_id.eq(creator_id)].copy()
    cost = float(forced.iloc[0].execution_cost_usd)
    if cost > budget:
        raise ValueError('强制加入不可行：单人报价超过预算。请先明确调整预算或报价。')
    remainder = model.loc[model.creator_id.ne(creator_id)].copy()
    rest = optimize_portfolio(remainder, round(budget-cost,2), objective, max_creators=5)
    selected = pd.concat([forced, rest.selected], ignore_index=True)
    result = PortfolioResult(selected, baseline.candidates, summarize(selected,budget), [])
    return baseline, result

def compare_results(baseline, changed):
    rows=[]
    for key, value in baseline.metrics.items():
        new=changed.metrics[key]
        rows.append(dict(metric=key, baseline=value, changed=new, delta=new-value if value is not None and new is not None else None))
    return pd.DataFrame(rows)

def effect_scenario(model, budget, objective, reach_multiplier=1., engagement_rate=.05, ctr=.01, cvr=.02):
    if not 0 <= reach_multiplier <= 10 or not all(0 <= x <= 1 for x in [engagement_rate,ctr,cvr]):
        raise ValueError('效果假设超出范围。')
    baseline = run_plan(model,budget,objective)
    changed=model.copy(deep=True)
    changed['estimated_reach']=(changed.estimated_reach*reach_multiplier).round()
    changed['engagement_rate']=engagement_rate
    optimized=run_plan(changed,budget,objective,ctr,cvr)
    ids=set(baseline.selected.get('creator_id',[]))
    fixed=optimized.candidates.loc[optimized.candidates.creator_id.isin(ids)].copy() if not optimized.candidates.empty else pd.DataFrame()
    return baseline, PortfolioResult(fixed,optimized.candidates,summarize(fixed,budget),[]), optimized

def decision_details(tables, supplement, result, objective):
    rows=[]
    selected=set(result.selected.get('creator_id',[]))
    evidence=tables['evidence']
    reviews=tables['reviews'].set_index('creator_id')
    candidates=result.candidates.set_index('creator_id') if not result.candidates.empty else pd.DataFrame()
    for r in supplement.itertuples():
        posts=evidence.loc[evidence.creator_id.eq(r.creator_id) & evidence.verification_status.eq('verified')]
        available=r.creator_id in candidates.index
        cost=float(candidates.loc[r.creator_id,'execution_cost_usd']) if available else None
        contribution=float(candidates.loc[r.creator_id,OUTCOME_COLUMNS[objective]]) if available else None
        fit_rejected=reviews.loc[r.creator_id,'fit_status']=='rejected'
        category='产品适配审核未通过' if fit_rejected else '入选模拟组合' if r.creator_id in selected else '缺少必要证据或不在计算范围' if not available else '单人超预算' if cost>result.metrics['budget_usd'] else '人数上限及预算组合取舍' if len(selected)==6 else '预算组合整体效果取舍'
        rows.append(dict(creator_id=r.creator_id, decision_category=category, hicreator_match_rate=r.hicreator_match_rate,
            hicreator_avg_views=r.hicreator_avg_views, hicreator_median_views=r.hicreator_median_views, hicreator_engagement_rate=r.hicreator_engagement_rate,
            verified_posts='；'.join(posts.post_url.map(text)) or 'Unknown：无已核验原帖，不能声称真实内容支持',
            simulated_cost=cost, simulated_objective_contribution=contribution,
            comparison_basis='在相同预算与最多6人下最大化累计模拟目标效果；不证明真实商业效果。可在强制加入中检验替换损失。',
            evidence_source=r.evidence_source, evidence_status=r.evidence_status, collected_at=r.collected_at))
    return pd.DataFrame(rows)
