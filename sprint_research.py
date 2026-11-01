"""Traceable, offline assisted screening. No live AI/API or inferred observations."""
from pathlib import Path
from datetime import datetime, timezone
import json
import uuid
import math

import pandas as pd

from creator_registry import REGISTRY_DIR, STAGES, FILES, validate_registry, audit_registry

VERSION = 'sprint-screen-v1'
RULES = {
    '猫咪生活': ('猫咪', '养猫', '猫主人', '猫的'),
    '宠物护理': ('护理', '梳毛', '健康', '美容'),
    '宠物喂养': ('喂食', '喂养', '营养', '猫粮', '宠物食品', '喂宠'),
    '宠物科技': ('智能', '科技', '摄像头', '自动'),
    '智能喂食器': ('自动喂', '智能喂', '喂食器', '喂宠器'),
    '宠物产品测评': ('测评', '开箱', '评测'),
    '品牌或制造商账号': ('品牌频道', '制造商', '设计师和制造商'),
}


def text(value):
    return '' if pd.isna(value) else str(value)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def screen_accounts(accounts):
    """Only descriptive source fields are classified; handles never imply a topic."""
    rows = []
    for _, account in accounts.iterrows():
        source = '；'.join(text(account.get(f)) for f in ('reported_description', 'reported_position'))
        matches = {label: [term for term in terms if term in source] for label, terms in RULES.items()}
        matches = {label: terms for label, terms in matches.items() if terms}
        brand = '品牌或制造商账号' in matches
        priority = sum(weight for label, weight in [('宠物喂养', 3), ('智能喂食器', 5),
                       ('宠物科技', 2), ('宠物产品测评', 2)] if label in matches)
        if '多猫' in source:
            priority += 2
        fields = ('profile_url', 'reported_description', 'reported_position', 'reported_followers',
                  'creator_region', 'reported_language', 'reported_median_views', 'reported_mean_engagement_rate')
        risks = ['HiCreator 第三方描述与指标，尚未独立核验；指标窗口和分母未知',
                 '创作者地区不等于美国受众占比；商业授权、排他协议未知']
        if brand:
            risks.append('来源定位提示品牌或制造商，当前正式创作者池排除')
        if text(account.account_id_precision_status) == 'precision_loss_risk':
            risks.append('来源数值账号 ID 存在精度损失风险')
        if text(account.cross_platform_name_hint).startswith('是'):
            risks.append('跨平台同名不代表同一人，身份须另行核验')
        rows.append(dict(creator_id=account.creator_id, platform=account.platform, handle=account.handle,
            categories='、'.join(matches) or 'Unknown',
            classification_basis='；'.join(f'{k}：描述/定位命中「{"、".join(v)}」' for k, v in matches.items()) or '描述/定位无明确线索；不根据名称推断',
            source_reference=f'{account.data_source} / {account.source_file} / {account.source_sheet} 第{account.source_row}行',
            source_excerpt=source, profile_completeness=sum(bool(text(account.get(f))) for f in fields) / len(fields),
            missing_fields='、'.join(f for f in fields if not text(account.get(f))) or '无',
            reported_followers=account.reported_followers, reported_median_views=account.reported_median_views,
            reported_mean_engagement_rate=account.reported_mean_engagement_rate,
            metric_assessment='仅展示第三方报告值；不推导广告 CTR、触达或订单',
            subject_risk='品牌/制造商线索' if brand else 'Unknown：主体待人工核验',
            petkit_clue='喂食器/多猫等场景线索，未证明 PETKIT 合作或双仓使用' if priority else 'Unknown',
            priority=0 if brand else priority,
            ai_status='AI 不建议优先审核' if brand else 'AI 初筛完成' if matches else 'AI 证据不足',
            human_status='待核验', risks='；'.join(risks), analysis_method='离线规则辅助；无实时模型 API', version=VERSION))
    result = pd.DataFrame(rows)
    focus = result.loc[result.subject_risk.ne('品牌/制造商线索')].sort_values(
        ['priority', 'creator_id'], ascending=[False, True]).groupby('platform', sort=True).head(4)
    result['focus_candidate'] = result.creator_id.isin(focus.creator_id)
    result.loc[result.focus_candidate, 'ai_status'] = 'AI 建议重点审核'
    return result


def deep_research(screen):
    """Source-level hypotheses, never claimed as watched/verified posts."""
    rows = []
    for _, row in screen.loc[screen.focus_candidate].iterrows():
        topics = row.categories
        def finding(label):
            return '第三方描述有线索，原帖待核验' if label in topics else 'Unknown：现有描述未提供充分证据'
        rows.append(dict(creator_id=row.creator_id, platform=row.platform, handle=row.handle,
            feeding=finding('宠物喂养'), smart_devices=finding('宠物科技'), product_reviews=finding('宠物产品测评'),
            dual_hopper_fit='喂食场景可进一步核对干粮、份量控制及多猫需求；双仓实际使用 Unknown' if '宠物喂养' in topics or '智能喂食器' in topics else 'Unknown：需核对干粮喂养与双仓需求',
            objective_hypothesis='Conversion：测评/设备演示线索，需验证行动引导与购买路径' if '宠物产品测评' in topics else 'Engagement / Brand Awareness：日常内容线索，需验证互动与受众',
            risks=row.risks + ('；生食/湿粮场景不必然适合干粮喂食器' if any(t in row.source_excerpt for t in ('生食', '生骨肉', '湿粮')) else ''),
            evidence_reference=row.source_reference, supporting_text=row.source_excerpt,
            analysis_scope='仅分析 HiCreator 公开导出描述；未观看视频；AI/规则推断，非核实事实',
            posts_requested=3, posts_collected=0, recentness='Unknown：无法判断近期内容覆盖',
            next_action='打开主页，补充最近 2–3 条原帖 URL、日期和可见指标；确认主体、美国受众及产品场景',
            ai_status='AI 证据不足', human_status='待核验'))
    return pd.DataFrame(rows)


def apply_event(tables, event):
    """Human-only append events overlay originals; existing CSVs are never overwritten."""
    if not text(event.get('reviewer')) or not text(event.get('reason')):
        raise ValueError('人工操作必须填写审核人与依据。')
    result = {k: v.copy(deep=True) for k, v in tables.items()}
    for key, records in event['updates'].items():
        if key not in FILES:
            raise ValueError('未知审核表。')
        table = result[key]
        primary = 'evidence_id' if key == 'evidence' else 'creator_id'
        for record in records:
            if key == 'accounts' and set(record) - {'creator_id', 'confirmed_subject_type'}:
                raise ValueError('人工日志不得覆盖原始账号和第三方来源字段。')
            if set(record) - set(FILES[key][1]):
                raise ValueError('审核包含未知字段。')
            if primary not in record:
                raise ValueError('审核缺少主键。')
            mask = table[primary].eq(record[primary]).fillna(False)
            if mask.any():
                for field, value in record.items():
                    table.loc[mask, field] = value
            else:
                if key in ('accounts', 'reviews'):
                    raise ValueError('不得用人工审核新增或替换账号身份。')
                table = pd.concat([table, pd.DataFrame([record])], ignore_index=True)
        result[key] = table
    return validate_registry(result)


def load_human_reviews(tables, directory=REGISTRY_DIR / 'human_reviews'):
    from deployment_policy import is_local_development
    if not is_local_development():
        return tables
    result = tables
    for path in sorted(Path(directory).glob('*.json')):
        result = apply_event(result, json.loads(path.read_text(encoding='utf-8')))
    return result


def save_human_review(tables, updates, reviewer, reason, directory=REGISTRY_DIR / 'human_reviews'):
    from deployment_policy import require_server_write
    require_server_write('保存人工审核或内容证据')
    event = dict(reviewer=reviewer.strip(), reason=reason.strip(), updates=updates,
                 timestamp=datetime.now(timezone.utc).isoformat())
    validated = apply_event(tables, event)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    filename = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '-' + uuid.uuid4().hex + '.json'
    with (directory / filename).open('x', encoding='utf-8') as stream:
        json.dump(event, stream, ensure_ascii=False, indent=2)
    return validated


DIMENSIONS = ('产品内容适配度', '内容表现', '互动表现', '数据证据可信度', '模拟预算效率')
SCORE_WEIGHTS = {
    'Brand Awareness': (.25, .35, .10, .20, .10),
    'Engagement': (.25, .10, .35, .20, .10),
    'Conversion': (.30, .10, .10, .20, .30),
}


def score_registry(tables, screen, objective='Brand Awareness', model=None, fit_keyword_groups=None):
    """Unknown dimensions stay None. No renormalized total on incomplete evidence."""
    weights = SCORE_WEIGHTS[objective]
    audit = audit_registry(tables).set_index('creator_id')
    model_index = model.set_index('creator_id') if model is not None and not model.empty else None
    rows = []
    for _, row in screen.iterrows():
        evidence = tables['evidence'].loc[tables['evidence'].creator_id.eq(row.creator_id)]
        verified = evidence.loc[evidence.verification_status.eq('verified')]
        # Content fit needs a traceable, human-verified post; source descriptions alone are insufficient.
        fit = None
        if not verified.empty:
            topics = '；'.join(verified.content_topic.map(text))
            groups = fit_keyword_groups if fit_keyword_groups is not None else [('喂食', '喂养', '猫粮'), ('智能', '自动', '科技'), ('测评', '演示', '开箱'), ('多猫', '双仓', '份量')]
            fit = sum(100 / len(groups) for terms in groups if any(t in topics for t in terms)) if groups else None
        views = number(row.reported_median_views)
        er = number(row.reported_mean_engagement_rate)
        performance = min(views / 100000 * 100, 100) if views is not None else None
        engagement = min(er / .10 * 100, 100) if er is not None else None
        approved = sum(tables['reviews'].set_index('creator_id').loc[row.creator_id, f'{s}_status'] == 'approved' for s in STAGES)
        # Zero here is measured coverage of verified evidence, not imputation of an unknown metric.
        confidence = min(len(verified), 3) / 3 * 50 + approved / 5 * 50
        efficiency = None
        efficiency_basis = 'Unknown：未配置独立模拟参数'
        if model_index is not None and row.creator_id in model_index.index:
            m = model_index.loc[row.creator_id]
            outcome = float(m.estimated_reach) * float(m.audience_match_score) / 100
            cap = 100
            if objective == 'Engagement':
                outcome *= float(m.engagement_rate)
                cap = 8
            elif objective == 'Conversion':
                outcome *= float(m.assumed_ctr) * float(m.assumed_click_to_purchase_cvr)
                cap = .04
            efficiency = min(outcome / float(m.estimated_fee_usd) / cap * 100, 100)
            efficiency_basis = f'模拟目标效果 {outcome:.2f} ÷ 模拟报价 ${m.estimated_fee_usd:.2f} ÷ 固定上限 {cap} ×100，封顶100'
        values = (fit, performance, engagement, confidence, efficiency)
        complete = sum(v is not None for v in values) / 5
        rows.append(dict(creator_id=row.creator_id, platform=row.platform, handle=row.handle,
            **dict(zip(DIMENSIONS, values)),
            total_score=sum(v * w for v, w in zip(values, weights)) if complete == 1 else None,
            known_contribution=sum(v * w for v, w in zip(values, weights) if v is not None),
            score_completeness=complete, evidence_coverage=min(len(verified), 3) / 3,
            content_fit_basis=('已核验帖子主题按配置关键词组等权计分：' + str(fit_keyword_groups or [('喂食', '喂养', '猫粮'), ('智能', '自动', '科技'), ('测评', '演示', '开箱'), ('多猫', '双仓', '份量')]) + '；需人工确认语义') if fit is not None else 'Unknown：无人工核验原帖，不按账号名称或第三方描述补分',
            performance_basis='HiCreator 中位播放量÷100,000×100，封顶100；窗口未知，不等于触达' if views is not None else 'Unknown',
            engagement_basis='HiCreator 平均互动率÷10%×100，封顶100；非广告CTR，分母待核验' if er is not None else 'Unknown',
            confidence_basis=f'已核验原帖覆盖 {len(verified)}/3（50%）＋已批准审核 {approved}/5（50%）；这是覆盖度规则',
            efficiency_basis=efficiency_basis,
            supporting_posts='；'.join(verified.post_url.map(text)) or 'Unknown：没有已核验原帖',
            model_eligible=bool(audit.loc[row.creator_id, 'model_eligible']),
            exclusion_reason=audit.loc[row.creator_id, 'pending_reasons'],
            change_conditions='补齐并批准原帖、身份/主体/适配审核和独立假设后重算；报价、预算或目标变化可改变组合',
            risks=row.risks))
    return pd.DataFrame(rows)
