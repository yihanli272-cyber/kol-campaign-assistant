"""Registry adapters and scenarios. Delegates all portfolio search to portfolio.py."""
import pandas as pd

from creator_registry import audit_registry, PARAMETERS
from kol_data import REQUIRED_FIELDS, validate_kol_data
from portfolio import optimize_portfolio, forecast_creators, summarize, PortfolioResult, OUTCOME_COLUMNS
from sprint_research import number, text

ASSUMPTION_VERSION = 'registry-sprint-v1'
PRESETS = (
    (450, 16000, .035), (800, 27000, .065), (1250, 48000, .028), (1800, 60000, .085),
    (600, 21000, .075), (950, 39000, .025), (1500, 65000, .045), (2200, 78000, .055),
    (700, 25000, .050), (1100, 46000, .040), (1700, 72000, .030), (2500, 90000, .060),
)
ASSUMPTION_LEVELS = {'Conservative': (.005, .01), 'Base': (.01, .02), 'Optimistic': (.015, .03)}


def sandbox_assumptions(accounts, screen):
    """Deliberately independent of historic views, followers, reported ER and inferred fit."""
    focus = screen.loc[screen.focus_candidate].sort_values(['platform', 'creator_id'])
    rows = []
    for (_, account), (fee, reach, er) in zip(focus.iterrows(), PRESETS):
        rows.append(dict(creator_id=account.creator_id, platform=account.platform,
            estimated_fee_usd=fee, estimated_reach=reach, assumed_engagement_rate=er,
            assumed_ctr=.01, assumed_cvr=.02, assumed_audience_match_score=100,
            assumed_content_quality_score=50,
            planning_basis='独立教学模板，按平台及编号顺序分配；不使用历史播放/粉丝推导触达；匹配100仅表示不调整模拟触达，质量50不用于真实内容判断',
            assumption_status='pending', model_data_type='simulated', assumption_version=ASSUMPTION_VERSION))
    return pd.DataFrame(rows)


def adapt_model(tables, screen, sandbox=False):
    assumptions = sandbox_assumptions(tables['accounts'], screen) if sandbox else tables['assumptions']
    eligible = set(audit_registry(tables).query('model_eligible').creator_id)
    rows = []
    for _, a in assumptions.iterrows():
        if not sandbox and a.creator_id not in eligible:
            continue
        if any(number(a.get(p)) is None for p in PARAMETERS):
            continue
        account = tables['accounts'].set_index('creator_id').loc[a.creator_id]
        rows.append(dict(creator_id=a.creator_id, creator_name=text(account.creator_name) or account.handle,
            handle=account.handle, platform=account.platform, creator_category='Pet technology planning',
            followers=number(account.reported_followers), engagement_rate=float(a.assumed_engagement_rate),
            estimated_fee_usd=float(a.estimated_fee_usd), estimated_reach=int(a.estimated_reach),
            audience_match_score=float(a.assumed_audience_match_score), content_quality_score=float(a.assumed_content_quality_score),
            assumed_ctr=float(a.assumed_ctr), assumed_click_to_purchase_cvr=float(a.assumed_cvr),
            data_type='third_party_registry_simulated_model', identity_data_type='third_party_reported',
            model_data_type='simulated', assumption_version=ASSUMPTION_VERSION,
            planning_basis=text(a.planning_basis), planning_mode='sandbox_unapproved' if sandbox else 'human_approved',
            source_assumption_version=text(a.assumption_version)))
    model = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[*REQUIRED_FIELDS, 'planning_mode'])
    return validate_kol_data(model) if not model.empty else model


def run_plan(model, budget=5000, objective='Brand Awareness', ctr=None, cvr=None, fee_overrides=None):
    data = model.copy(deep=True)
    for field, value in [('assumed_ctr', ctr), ('assumed_click_to_purchase_cvr', cvr)]:
        if value is not None:
            if number(value) is None or not 0 <= value <= 1:
                raise ValueError('CTR / CVR 必须为 0–1 的有限比率。')
            data[field] = float(value)
    for creator_id, fee in (fee_overrides or {}).items():
        if creator_id not in set(data.creator_id):
            raise ValueError('报价修改引用未知候选。')
        if number(fee) is None or fee <= 0 or round(fee, 2) != fee:
            raise ValueError('模拟报价必须为正数，最多两位小数。')
        data.loc[data.creator_id.eq(creator_id), 'estimated_fee_usd'] = fee
    result = optimize_portfolio(data, budget, objective)
    result.messages.append('所有效果与报价均为模拟；触达逐人累加未去重；不表示订单、市场报价或可合作承诺。')
    return result


def selection_explanations(tables, screen, result, objective):
    audit = audit_registry(tables).set_index('creator_id')
    selected = set(result.selected.get('creator_id', []))
    candidates = result.candidates.set_index('creator_id') if not result.candidates.empty else pd.DataFrame()
    rows = []
    for _, row in screen.iterrows():
        formal = bool(audit.loc[row.creator_id, 'model_eligible'])
        if row.creator_id in selected:
            reason = f'在预算和最多6人约束下，作为整体最优组合的一员最大化模拟 {objective}；非按单人评分取前几名'
            status = '组合入选（模拟）'
        elif row.creator_id not in candidates.index:
            status = '未进入计算'
            reason = '未进入当前平台/候选范围，或缺少独立模拟假设'
        else:
            candidate = candidates.loc[row.creator_id]
            if candidate.execution_cost_usd > result.metrics['budget_usd']:
                status, reason = '预算约束', '单人模拟执行成本超过总预算；降低报价或增加预算后重算'
            elif candidate[OUTCOME_COLUMNS[objective]] <= 0:
                status, reason = '目标效果为零', '当前模拟目标效果为0；检查触达、CTR、CVR或互动假设'
            else:
                status, reason = '组合优化取舍', '存在更优整体目标效果组合，受预算及6人上限约束；并非证明内容不适配'
        if row.subject_risk == '品牌/制造商线索':
            reason += '；第三方定位提示非独立创作者，需另行评估'
        rows.append(dict(creator_id=row.creator_id, status=status, reason=reason,
            formal_eligibility='具备资格' if formal else '资格不足：' + audit.loc[row.creator_id, 'pending_reasons'],
            change_conditions='完成缺失审核、补充原帖；改变预算/报价/目标/效果假设后重新运行；名单也可能不变'))
    return pd.DataFrame(rows)


def scenario_suite(model):
    """Canonical baseline, one variable family per comparison; no manufactured swaps."""
    baseline = run_plan(model, ctr=.01, cvr=.02)
    base_ids = set(baseline.selected.get('creator_id', []))
    rows = []
    def add(family, label, result, objective='Brand Awareness', mode='重新优化', ctr=.01, cvr=.02):
        ids = set(result.selected.get('creator_id', []))
        rows.append(dict(family=family, scenario=label, calculation=mode, objective=objective,
            selected_ids=', '.join(sorted(ids)) or '无', entered=', '.join(sorted(ids - base_ids)) or '无',
            exited=', '.join(sorted(base_ids - ids)) or '无', assumed_ctr=ctr, assumed_cvr=cvr,
            **result.metrics))
    for budget in (3000, 5000, 8000):
        add('预算变化', f'${budget:,}', run_plan(model, budget, ctr=.01, cvr=.02))
    for objective in OUTCOME_COLUMNS:
        add('目标变化', objective, run_plan(model, objective=objective, ctr=.01, cvr=.02), objective)
    for label, (ctr, cvr) in ASSUMPTION_LEVELS.items():
        recomputed = run_plan(model, ctr=ctr, cvr=cvr)
        add('效果假设', label, recomputed, ctr=ctr, cvr=cvr)
        fixed_data = recomputed.candidates.loc[recomputed.candidates.creator_id.isin(base_ids)].copy() if not recomputed.candidates.empty else pd.DataFrame()
        fixed = PortfolioResult(fixed_data, recomputed.candidates, summarize(fixed_data, 5000), [])
        add('效果假设', label, fixed, mode='固定基准组合', ctr=ctr, cvr=cvr)
    return pd.DataFrame(rows)


def safe_csv(frame):
    """Keep user and third-party text inert when opened by a spreadsheet."""
    result = frame.copy()
    for column in result.columns:
        result[column] = result[column].map(lambda v: "'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v)
    return result.to_csv(index=False).encode('utf-8-sig')
