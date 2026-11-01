"""One-day registry workspace. Original app stays available as an explicit legacy view."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import uuid

import pandas as pd
import streamlit as st

from creator_registry import load_registry, audit_registry, STAGES, PARAMETERS
from sprint_research import (screen_accounts, deep_research, score_registry, SCORE_WEIGHTS,
                             DIMENSIONS, load_human_reviews, save_human_review, text)
from sprint_decision import (adapt_model, sandbox_assumptions, run_plan, scenario_suite,
                             selection_explanations, ASSUMPTION_LEVELS, safe_csv)
from portfolio import export_portfolio_csv
from ui_layout import (apply_workspace_style, render_metrics, value_chart, outcome_charts,
                       comparison_charts, portfolio_change_charts, CHART_COLORS)

LABELS = {
    'creator_id': '记录编号', 'platform': '平台', 'handle': '账号', 'categories': '分类线索',
    'classification_basis': '分类依据', 'source_reference': '来源定位', 'source_excerpt': '第三方原始描述',
    'profile_completeness': '基础资料完整度', 'missing_fields': '未知字段',
    'reported_followers': '第三方报告粉丝数', 'reported_median_views': '第三方报告中位播放量',
    'reported_mean_engagement_rate': '第三方报告互动率', 'metric_assessment': '指标判断边界',
    'subject_risk': '主体风险', 'petkit_clue': '产品场景线索', 'ai_status': 'AI 状态',
    'human_status': '人工状态', 'risks': '风险', 'focus_candidate': '重点候选',
    'analysis_method': '方法', 'priority': '研究优先级（规则）', 'version': '规则版本',
    'total_score': '综合分（不完整时未知）', 'known_contribution': '已知维度贡献（非综合排名）',
    'score_completeness': '评分完整度', 'evidence_coverage': '已核验原帖覆盖（目标3条）',
    'supporting_posts': '支持原帖', 'model_eligible': '正式资格', 'exclusion_reason': '资格阻断原因',
    'change_conditions': '可能改变选择的条件', 'status': '组合状态', 'reason': '选择/淘汰理由',
    'formal_eligibility': '独立资格判断', 'family': '情景类型', 'scenario': '方案',
    'calculation': '计算方式', 'objective': '营销目标', 'selected_ids': '入选名单',
    'entered': '较基准进入', 'exited': '较基准退出',
    'post_url': '原帖链接', 'post_date': '发布日期', 'content_format': '内容形式',
    'content_topic': '公开主题/描述', 'visible_views': '可见播放', 'visible_likes': '可见点赞',
    'visible_comments': '可见评论', 'evidence_source': '证据来源', 'verification_status': '核验状态',
    'product_relevance_reason': '产品相关性依据', 'evidence_id': '证据编号', 'checked_at': '核验日期',
    'feeding': '喂养线索', 'smart_devices': '智能设备线索', 'product_reviews': '测评线索',
    'dual_hopper_fit': '双仓使用场景推断', 'objective_hypothesis': '目标适配假说',
    'evidence_reference': '分析来源', 'supporting_text': '支持描述', 'analysis_scope': '实际分析范围',
    'posts_requested': '待采集目标', 'posts_collected': '已采集原帖', 'recentness': '近期覆盖',
    'next_action': '待人工核验', 'planning_basis': '模拟参数依据', 'planning_mode': '规划模式',
    'estimated_fee_usd': '模拟报价（美元）', 'estimated_reach': '模拟单条触达',
    'assumed_engagement_rate': '模拟互动率', 'assumed_ctr': '模拟CTR', 'assumed_cvr': '模拟CVR',
    'assumed_audience_match_score': '模拟受众调整参数', 'assumed_content_quality_score': '旧优化器兼容参数',
    'assumption_status': '假设人工状态', 'model_data_type': '模型数据类型', 'assumption_version': '假设版本',
    'content_fit_basis': '内容适配计算依据', 'performance_basis': '内容表现计算依据',
    'engagement_basis': '互动计算依据', 'confidence_basis': '证据可信度计算依据', 'efficiency_basis': '预算效率计算依据',
    'creator_name': '达人名称', 'execution_cost_usd': '模拟执行成本（美元）',
    'target_reach': '模拟调整触达', 'projected_engagements': '模拟互动',
    'projected_clicks': '模拟点击', 'projected_conversions': '模拟转化（非订单）',
    'reported_mean_views': '第三方报告平均播放量', 'research_priority': '研究优先级',
    'intake_status': '资料接入', 'screening_status': '初筛进度', 'research_status': 'AI研究状态',
    'content_status': '内容证据状态', 'human_review_status': '人工审核状态',
    'verified_post_count': '已核验原帖数', 'evidence_basis': '证据/线索依据',
}
for _stage, _label in {'identity': '身份', 'content': '内容', 'fit': '产品适配', 'subject_type': '主体', 'model': '模型资格'}.items():
    for _suffix, _caption in {'status': '状态', 'reason': '依据', 'checked_by': '审核人', 'checked_at': '审核日期'}.items():
        LABELS[f'{_stage}_{_suffix}'] = f'{_label}{_caption}'
METRICS = {
    'budget_usd': '预算（美元）', 'spent_usd': '已使用预算（美元）', 'remaining_usd': '剩余预算（美元）',
    'creator_count': '入选人数', 'raw_reach': '模拟累计触达（未去重）', 'target_reach': '模拟调整触达（未去重）',
    'engagements': '模拟互动', 'clicks': '模拟点击', 'conversions': '模拟转化（非订单）',
    'cpm_usd': '模拟 CPM（美元）', 'cpe_usd': '模拟 CPE（美元）', 'cpc_usd': '模拟 CPC（美元）', 'cpa_usd': '模拟 CPA（美元）',
}
NOTICE = '第三方报告指标不代表本工具独立采集或实时监测；内容线索不等于已核验原帖。报价、触达、CTR、CVR及转化均为Simulation；累计触达未去重，非真实订单。'


def showcase_mode():
    return st.session_state.get('presentation_mode', 'Demo Showcase') == 'Demo Showcase'


def research_area(label):
    return st.expander(label, expanded=False) if showcase_mode() else st.container()


def display_value(value, percent=False):
    if value is None or pd.isna(value) or (isinstance(value, str) and value.strip() in ('', 'None', 'NaN', 'nan', 'Unknown', 'N/A')):
        return '未提供'
    if percent:
        return f'{float(value):.2%}'
    if isinstance(value, (int, float)):
        return f'{value:,.2f}'.removesuffix('.00')
    return str(value)


def decision_summary(frame, result):
    """Show selected rows plus the six research priorities, without changing selection."""
    ids = set(result.selected.get('creator_id', [])) | set(PRIORITY_IDS)
    main = frame.loc[frame.creator_id.isin(ids)]
    others = frame.loc[~frame.creator_id.isin(ids)]
    columns = [c for c in ['creator_id','platform','handle','status','reason','decision_category','simulated_cost','simulated_objective_contribution'] if c in main]
    table(main[columns])
    st.caption(f'重点及实际入选共 {len(main)} 位；其他 {len(others)} 位汇总于下方。不在当前计算范围不表示质量差。')
    if not others.empty:
        status = 'status' if 'status' in others else 'decision_category'
        table(others.groupby(status).size().rename('人数').reset_index())
    with st.expander('完整52位选择与排除记录'):
        table(frame)


def creator_cards(tables, screen, model, supplement, details):
    accounts = tables['accounts'].set_index('creator_id')
    studies = screen.set_index('creator_id')
    sources = supplement.set_index('creator_id')
    reasons = details.set_index('creator_id')
    params = model.set_index('creator_id')
    ids = [cid for cid in PRIORITY_IDS if cid in accounts.index]
    for index, cid in enumerate(ids):
        if index % 2 == 0:
            columns = st.columns(2)
        a, study = accounts.loc[cid], studies.loc[cid]
        with columns[index % 2], st.container(border=True):
            st.markdown(f'**{a.platform} · @{a.handle}**')
            st.caption(cid + ' · 首批重点研究 · 资料已接入 / 初筛已完成')
            st.link_button('账号主页', a.profile_url)
            st.caption('🔵 第三方报告（非实时或自采）')
            st.write(f'粉丝数 {display_value(a.reported_followers)} · 中位播放量 {display_value(a.reported_median_views)}')
            st.write(f'平均播放量 {display_value(a.reported_mean_views)} · 互动率 {display_value(a.reported_mean_engagement_rate, True)}')
            match = sources.loc[cid, 'hicreator_match_rate'] if cid in sources.index else None
            st.write('第三方匹配度：' + display_value(match, True))
            st.write('内容方向（资料线索）：' + display_value(study.categories))
            verified = tables['evidence'].loc[tables['evidence'].creator_id.eq(cid) & tables['evidence'].verification_status.eq('verified')]
            st.write('产品适配：'+('已有原帖证据，适配依据见详情。' if not verified.empty else '资料存在场景线索，原帖支持尚未提供。'))
            st.caption('🟢 Simulation / 模拟假设')
            m = params.loc[cid] if cid in params.index else {}
            st.write('模拟报价（USD）：' + display_value(m.get('estimated_fee_usd')))
            st.write('模拟CTR：' + display_value(m.get('assumed_ctr'),True) + ' · 模拟CVR：' + display_value(m.get('assumed_click_to_purchase_cvr'),True))
            if cid in reasons.index:
                r = reasons.loc[cid]
                st.write('当前组合：' + display_value(r.decision_category))
                st.write('模拟目标贡献：' + display_value(r.simulated_objective_contribution))
            with st.expander('Evidence & Verification · 来源与完整字段'):
                table(tables['accounts'].loc[tables['accounts'].creator_id.eq(cid)])
                table(details.loc[details.creator_id.eq(cid)])
                st.caption('正式资格由审核门槛独立决定；研究优先级及Simulation入选均不构成批准。')


def local_date():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def parse_campaign_config(raw):
    """Validate the whole upload before changing any session widget values."""
    if len(raw) > 65536:
        raise ValueError('配置文件不得超过64KB。')
    data = json.loads(raw.decode('utf-8-sig'))
    fields = ('brand', 'product', 'category', 'description', 'market', 'selling_points')
    if not isinstance(data, dict):
        raise ValueError('配置必须为JSON对象。')
    if set(data) - {*fields, 'fit_keyword_groups', 'budget_usd', 'objective', 'creator_registry_directory'}:
        raise ValueError('配置包含未知字段。')
    if not all(isinstance(data.get(k), str) and data[k].strip() and len(data[k]) <= 10000 for k in fields):
        raise ValueError('品牌、产品、类别、描述、市场和卖点必须是非空文本。')
    groups = data.get('fit_keyword_groups')
    if not isinstance(groups, list) or not 1 <= len(groups) <= 64 or not all(
            isinstance(g, list) and 1 <= len(g) <= 32 and all(
                isinstance(t, str) and t.strip() and len(t) <= 200 and not any(c in t for c in '\n\r,，') for t in g) for g in groups):
        raise ValueError('适配关键词必须为非空分组列表，组内词语不能含逗号或换行。')
    budget = data.get('budget_usd', 5000)
    objective = data.get('objective', 'Brand Awareness')
    if type(budget) is not int or not 0 <= budget <= 10000 or objective not in SCORE_WEIGHTS:
        raise ValueError('预算必须为0–10000的整数，营销目标必须是支持的三个目标之一。')
    # Dataset paths in the shipped defaults are deliberately not imported.
    return {**{k: data[k] for k in fields}, 'fit_keyword_groups': groups,
            'budget_usd': budget, 'objective': objective}


def import_campaign_config():
    uploaded = st.session_state.get('campaign_config_upload')
    if uploaded is None:
        return
    try:
        data = parse_campaign_config(uploaded.getvalue())
        updates = {'campaign_' + k: data[k] for k in ('brand', 'product', 'category', 'description', 'market', 'selling_points')}
        updates.update(campaign_keywords='\n'.join(','.join(g) for g in data['fit_keyword_groups']),
                       sprint_budget=data['budget_usd'], sprint_objective=data['objective'])
        st.session_state.update(updates)
        st.session_state['campaign_import_message'] = '配置已导入当前会话；未修改PETKIT默认文件或达人资料。'
        st.session_state.pop('campaign_import_error', None)
    except (ValueError, UnicodeError, TypeError) as exc:
        st.session_state['campaign_import_error'] = '配置导入失败：' + str(exc)
        st.session_state.pop('campaign_import_message', None)


def table(frame):
    config = {**LABELS, **METRICS}
    config['hicreator_match_rate'] = st.column_config.NumberColumn('第三方匹配度（非转化概率）', format='percent')
    config['post_url'] = st.column_config.LinkColumn('原帖链接')
    config['profile_url'] = st.column_config.LinkColumn('公开主页')
    for key in ('profile_completeness', 'score_completeness', 'evidence_coverage'):
        config[key] = st.column_config.NumberColumn(config[key], format='percent')
    display = frame.copy(deep=True)
    for column in display.columns:
        if display[column].isna().any() or display[column].map(lambda v: isinstance(v,str) and v.strip() in ('','None','nan','NaN','Unknown','N/A')).any():
            display[column] = display[column].map(display_value)
            config[column] = LABELS.get(column, METRICS.get(column, column))
    st.dataframe(display, hide_index=True, width='stretch', height='auto', row_height=88, column_config=config)


PRIORITY_IDS = ('KOL-014', 'KOL-006', 'KOL-025', 'KOL-022', 'KOL-041', 'KOL-044')
# Existing report leads only; none of these entries asserts an accessible original post.
PRIORITY_LEADS = {
    'KOL-014': ('https://www.modash.io/content-library/brands/petsfit-examples', '既有内容报告记录的旧Petsfit二手索引；日期与原帖待核实'),
    'KOL-006': ('https://www.modash.io/content-library/brands/petlibro-examples', '既有内容报告记录的PETLIBRO二手索引；原帖与排他关系待核实'),
    'KOL-025': ('https://www.modash.io/content-library/brands/pupford-examples', '既有内容报告记录的Pupford旧内容索引；不是近期喂食器实测证据'),
}


def priority_creator_view(tables, screen, audit):
    """Presentation only: research progress never grants approval or eligibility."""
    accounts = tables['accounts'].set_index('creator_id')
    research = screen.set_index('creator_id')
    reviews = tables['reviews'].set_index('creator_id')
    eligibility = audit.set_index('creator_id')
    rows = []
    for cid in PRIORITY_IDS:
        if cid not in accounts.index:
            continue
        account, study, review = accounts.loc[cid], research.loc[cid], reviews.loc[cid]
        posts = tables['evidence'].loc[tables['evidence'].creator_id.eq(cid)]
        verified = posts.loc[posts.verification_status.eq('verified')]
        pending = posts.loc[posts.verification_status.eq('pending') & posts.post_url.notna() & posts.post_url.ne('')]
        lead = PRIORITY_LEADS.get(cid)
        states = [review[f'{stage}_status'] for stage in STAGES]
        rows.append(dict(creator_id=cid, platform=account.platform, handle=account.handle,
            reported_followers=account.reported_followers, reported_mean_views=account.reported_mean_views,
            reported_median_views=account.reported_median_views,
            reported_mean_engagement_rate=account.reported_mean_engagement_rate,
            research_priority='首批重点审核',
            intake_status='已接入' if study.profile_completeness == 1 else '资料不完整',
            screening_status='已完成初筛', research_status='重点研究对象',
            content_status='已核验' if not verified.empty else '已找到线索，待核实' if not pending.empty or lead else '待补充证据',
            human_review_status='未通过' if 'rejected' in states else '已通过' if all(s == 'approved' for s in states) else '待审核',
            model_eligible=bool(eligibility.loc[cid, 'model_eligible']),
            verified_post_count=len(verified),
            evidence_basis='；'.join(verified.post_url.map(text)) if not verified.empty else '；'.join(pending.post_url.map(text)) if not pending.empty else (lead[0] + '；' + lead[1]) if lead else '尚未取得可追溯原帖；第三方账号描述不算原帖证据',
            risks=study.risks, missing_fields=study.missing_fields,
            exclusion_reason=eligibility.loc[cid, 'pending_reasons']))
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def cached_suite(model):
    return scenario_suite(model)


def human_forms(tables, account, directory=None):
    """All persistence happens only in response to an explicit form submission."""
    from deployment_policy import is_local_development
    if not is_local_development():
        st.caption('公开展示模式：研究资料只读，人工证据与审核保存功能已禁用。')
        return
    creator_id = account.creator_id
    with st.expander('人工核验：录入原帖证据'):
        st.caption('填写实际查看的公开信息。未知指标留空；无法观看时在来源中写明“仅标题/描述，未观看视频”。不会自动批准账号。')
        with st.form('evidence_form_' + creator_id):
            url = st.text_input('原帖 URL（HTTPS）', key='evidence_url_' + creator_id)
            published = st.text_input('原帖日期（YYYY-MM-DD，未知留空）')
            content_format = st.selectbox('内容形式', ['短视频', '长视频', '图文', 'Unknown'])
            topic = st.text_area('实际可见标题、描述或内容摘要')
            relevance = st.text_area('与当前产品的关系及判断依据')
            source = st.text_input('数据来源与访问范围', value='人工查看公开标题或描述，未观看视频')
            cols = st.columns(3)
            views = cols[0].text_input('可见播放量（未知留空）')
            likes = cols[1].text_input('可见点赞数（未知留空）')
            comments = cols[2].text_input('可见评论数（未知留空）')
            reviewer = st.text_input('证据录入人')
            verified = st.checkbox('我已核对原帖、日期和上述可见信息，将此条证据标为已核验')
            submitted = st.form_submit_button('保存这条人工证据')
        if submitted:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                allowed = {'Instagram': ('instagram.com',), 'TikTok': ('tiktok.com',), 'YouTube': ('youtube.com', 'youtu.be')}[account.platform]
                if parsed.scheme != 'https' or not any(parsed.hostname == host or (parsed.hostname or '').endswith('.' + host) for host in allowed):
                    raise ValueError('原帖必须属于当前平台的 HTTPS 地址。')
                record = dict(evidence_id='H-' + uuid.uuid4().hex, creator_id=creator_id, platform=account.platform,
                    post_url=url, post_date=published, content_format=content_format, content_topic=topic,
                    visible_views=views, visible_likes=likes, visible_comments=comments,
                    evidence_source=source, checked_at=local_date(),
                    verification_status='verified' if verified else 'pending', product_relevance_reason=relevance)
                save_human_review(tables, {'evidence': [record]}, reviewer, relevance, **({'directory': directory} if directory else {}))
                st.success('原帖已保存；账号审核资格保持独立。')
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    with st.expander('人工核验：五阶段审核与模拟假设'):
        st.caption('需要你逐阶段实际确认。只有完整批准全部阶段、确认主体、存在已核验原帖及批准独立假设后，才能进入正式池。操作以新增审核日志保存，不覆盖原始 CSV。')
        current = tables['reviews'].set_index('creator_id').loc[creator_id]
        statuses = {'待核验': 'pending', '已批准': 'approved', '退回修改': 'rejected'}
        stage_labels = {'identity': '身份', 'content': '内容', 'fit': '产品适配', 'subject_type': '账号主体', 'model': '模型资格'}
        with st.form('review_form_' + creator_id):
            reviewer = st.text_input('审核人', key='human_reviewer_' + creator_id)
            reason = st.text_area('审核依据（注明原帖/资料及适用阶段）', key='human_reason_' + creator_id)
            values = {}
            for stage in STAGES:
                status = current[f'{stage}_status']
                values[stage] = st.selectbox(stage_labels[stage] + '审核', list(statuses), index=list(statuses.values()).index(status), key='review_' + stage + '_' + creator_id)
            subjects = ['', 'creator', 'pet_account', 'multi_pet_household', 'brand', 'manufacturer', 'other']
            subject = st.selectbox('人工确认主体（空白表示未知）', subjects,
                index=subjects.index(text(account.confirmed_subject_type)) if text(account.confirmed_subject_type) in subjects else 0)
            st.write('可选：配置并确认该账号独立模拟假设（与第三方指标无关）')
            old = tables['assumptions'].loc[tables['assumptions'].creator_id.eq(creator_id)]
            fields = {'estimated_fee_usd': ('模拟报价 $', 500., 1., 1000000.), 'estimated_reach': ('模拟触达', 20000., 0., 10000000.),
                'assumed_engagement_rate': ('模拟互动率（0–1）', .05, 0., 1.), 'assumed_ctr': ('模拟 CTR（0–1）', .01, 0., 1.),
                'assumed_cvr': ('模拟 CVR（0–1）', .02, 0., 1.), 'assumed_audience_match_score': ('模拟受众调整参数（0–100）', 100., 0., 100.),
                'assumed_content_quality_score': ('旧优化器兼容质量参数（不是真实内容评分）', 50., 0., 100.)}
            params = {f: st.number_input(label, min_value=low, max_value=high,
                value=float(old.iloc[0][f]) if not old.empty and pd.notna(old.iloc[0][f]) else default, key='param_' + f + '_' + creator_id)
                for f, (label, default, low, high) in fields.items()}
            basis = st.text_area('逐项模拟参数依据（将保存为各参数来源说明）')
            approve_assumptions = st.checkbox('我确认这些为模拟假设，并批准用于规划')
            confirm = st.checkbox('我已实际审核上述各阶段；此次操作代表我的人工确认')
            submitted = st.form_submit_button('保存人工审核')
        if submitted:
            try:
                if not confirm:
                    raise ValueError('请由实际审核者勾选人工确认后保存。')
                today = local_date()
                review = {'creator_id': creator_id}
                for stage, status in values.items():
                    review.update({f'{stage}_status': statuses[status], f'{stage}_reason': reason,
                        f'{stage}_checked_by': reviewer, f'{stage}_checked_at': today})
                updates = {'reviews': [review], 'accounts': [{'creator_id': creator_id, 'confirmed_subject_type': subject}]}
                if approve_assumptions:
                    if not basis.strip():
                        raise ValueError('请填写每项模拟参数的来源或设置理由。')
                    assumption = dict(creator_id=creator_id, platform=account.platform, content_format='一条内容（模拟）',
                        model_data_type='simulated', assumption_version='human-sprint-v1', assumption_status='approved',
                        planning_basis=basis, engagement_rate_basis='reach', checked_by=reviewer, checked_at=today, **params)
                    assumption.update({f + '_source': f + '：' + basis for f in PARAMETERS})
                    updates['assumptions'] = [assumption]
                save_human_review(tables, updates, reviewer, reason, **({'directory': directory} if directory else {}))
                st.success('人工审核已保存。正式资格仍由前置门槛重新计算。')
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def render_sprint():
    apply_workspace_style()
    st.title('AI KOL Campaign Decision Assistant')
    st.caption('独立开发的通用营销决策工具：跨平台达人研究、目标匹配、预算组合优化、决策解释与情景模拟。PETKIT仅为默认演示案例。')
    defaults = json.loads(Path(__file__).with_name('campaign_config.json').read_text(encoding='utf-8'))
    registry_dir = Path(__file__).parent / defaults.pop('creator_registry_directory', 'data/creator_registry')
    try:
        tables = load_human_reviews(load_registry(registry_dir), directory=registry_dir / 'human_reviews')
        screen = screen_accounts(tables['accounts'])
        deep = deep_research(screen)
        audit = audit_registry(tables)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        st.error('研究数据或人工审核日志读取失败：' + str(exc))
        st.stop()
    reviews = tables['reviews'].set_index('creator_id')
    for index, row in screen.iterrows():
        states = [reviews.loc[row.creator_id, f'{stage}_status'] for stage in STAGES]
        screen.loc[index, 'human_status'] = '退回修改' if 'rejected' in states else '已批准' if all(s == 'approved' for s in states) else '待核验'
    from guided_trial_ui import render_trial, open_trial
    if st.session_state.get('trial_active',False):
        render_trial(tables,screen,defaults,registry_dir / 'hicreator_supplement.csv')
        return
    st.button('Guided Trial · 新手引导体验',key='open_guided_trial',on_click=open_trial)
    with st.sidebar:
        st.radio('展示模式', ['Demo Showcase', 'Research Workspace'], key='presentation_mode')
        st.header('Campaign 活动参数')
        with st.expander('品牌与产品配置'):
            st.file_uploader('导入已下载的Campaign配置（JSON）', type=['json'], key='campaign_config_upload', on_change=import_campaign_config)
            if st.session_state.get('campaign_import_error'):
                st.error(st.session_state['campaign_import_error'])
            elif st.session_state.get('campaign_import_message'):
                st.success(st.session_state['campaign_import_message'])
            campaign = {key: st.text_input(label, value=defaults[key], key='campaign_' + key) for key, label in [('brand','品牌'), ('product','产品'), ('category','产品类别'), ('description','产品描述'), ('market','目标市场'), ('selling_points','核心卖点')]}
            keyword_text = st.text_area('适配关键词（每行一组，组内逗号分隔）', value='\n'.join(','.join(g) for g in defaults['fit_keyword_groups']), key='campaign_keywords')
            groups = [[term.strip() for term in line.replace('，', ',').split(',') if term.strip()] for line in keyword_text.splitlines() if line.strip()]
            campaign['fit_keyword_groups'] = groups
            st.caption('修改保留在当前会话；完整刷新前可下载 Campaign 配置，之后在此导入恢复，不会覆盖默认文件。' if showcase_mode() else '修改仅保留在当前会话；完整刷新或重启前，请到报告页下载配置，之后在此导入恢复。不会覆盖PETKIT默认文件，不自动校准教学模板、第三方匹配度或跨产品沿用人工批准。')
        objective = st.selectbox('营销目标', list(SCORE_WEIGHTS), key='sprint_objective')
        budget = st.number_input('模拟总预算（美元）', min_value=0, max_value=10000, value=5000, step=100, key='sprint_budget')
        mode = '研究情景演练（未批准）' if showcase_mode() else st.radio('计算范围', ['研究情景演练（未批准）', '正式推荐（仅已批准）'], key='sprint_mode')
        platforms = st.multiselect('平台筛选', ['Instagram', 'TikTok', 'YouTube'], default=['Instagram', 'TikTok', 'YouTube'], key='sprint_platforms')
        level = 'Base' if showcase_mode() else st.selectbox('模拟效果假设', list(ASSUMPTION_LEVELS), index=1, key='sprint_assumption')
        if not showcase_mode():
            st.caption('情景演练仅使用12位重点候选的独立教学模板，不授予正式资格。')
    if not groups or any(not group for group in groups):
        st.error('请提供至少一组非空适配关键词。')
        st.stop()
    config_changed = any(campaign[k] != defaults[k] for k in defaults)
    st.caption(f"{campaign['brand']} · {campaign['product']} · {campaign['market']}")
    if showcase_mode():
        from showcase_ui import render_showcase
        render_showcase(tables, screen, campaign, budget, objective, platforms, supplement_path=registry_dir / 'hicreator_supplement.csv')
        return
    if config_changed:
        st.warning('Campaign配置已改变：当前52条资料及12人研究优先级仍是PETKIT演示模板。原第三方匹配度仅对应原搜索任务；旧人工批准不适用于新配置，正式计算暂停。请重新核对产品适配。')
    sandbox = mode.startswith('研究')
    model = adapt_model(tables, screen, sandbox=sandbox)
    model = model.loc[model.platform.isin(platforms)]
    if config_changed and not sandbox:
        model = model.iloc[:0].copy()
    if len(model) > 30:
        st.error('现有优化器最多支持30位候选。请用平台筛选将正式计算范围缩小到30位以内。')
        st.stop()
    ctr, cvr = ASSUMPTION_LEVELS[level]
    result = run_plan(model, budget, objective, ctr=ctr, cvr=cvr)
    # Scores use the same current scenario rates as the portfolio efficiency inputs.
    score_model = model.copy()
    score_model['assumed_ctr'], score_model['assumed_click_to_purchase_cvr'] = ctr, cvr
    scores = score_registry(tables, screen, objective, score_model, fit_keyword_groups=groups)
    explanations = selection_explanations(tables, screen, result, objective)
    focus = screen.loc[screen.focus_candidate]
    if sandbox:
        st.warning('当前为待审核研究情景演练：组合不能作为正式推荐。正式资格 ' + str(int(audit.model_eligible.sum())) + ' / 52；高分与模拟入选均不会自动批准账号。')
    else:
        st.info('正式推荐仅计算通过全部审核及独立假设门槛的账号；预测仍然是模拟。')
    st.caption(NOTICE)
    overview, database, recommendation, scenarios, report = st.tabs([
        'Campaign Overview · 总览', 'Creator Database · 达人研究', 'KOL Recommendation · 评分与推荐',
        'Scenario Comparison · 情景对比', 'Report & Export · 报告导出'])
    with overview:
        top = st.columns(3)
        top[0].metric('Campaign Budget（Simulation USD）', f"${budget:,.0f}")
        top[1].metric('Creator Pool（第三方账号）', len(screen))
        top[2].metric('Priority Creators（研究名单）', int(screen.creator_id.isin(PRIORITY_IDS).sum()))
        estimates = st.columns(3)
        for col, field, label in zip(estimates, ['target_reach','engagements','conversions'], ['Estimated Reach（Simulation 未去重）','Estimated Engagement（Simulation）','Estimated Conversions（Simulation）']):
            col.metric(label, f"{result.metrics[field]:,.2f}")
        used = result.metrics['spent_usd'] / budget if budget else 0.
        st.progress(min(1.,used), text=f"Simulation · 预算已使用 {used:.1%}；剩余 ${result.metrics['remaining_usd']:,.2f}")
        distribution = tables['accounts'].groupby('platform').size().rename('账号数').reset_index()
        st.markdown('**平台达人分布 · 第三方账号数**')
        st.vega_lite_chart(distribution, {'height':240, 'padding':{'top':16,'bottom':16,'left':16,'right':16},
            'mark':{'type':'arc','innerRadius':55}, 'encoding':{'theta':{'field':'账号数','type':'quantitative'},
            'color':{'field':'platform','type':'nominal','title':'平台','legend':{'orient':'bottom'},'scale':{'range':CHART_COLORS}},
            'tooltip':[{'field':'platform','title':'平台'},{'field':'账号数'}]}}, width='stretch')
        with st.expander('Campaign效果概览 · Simulation'):
            outcome_charts(pd.DataFrame([dict(方案='当前组合',**result.metrics)]),'方案','当前组合效果')
        st.caption('真实账号规模与模拟效果分开呈现；研究入选不代表已批准，正式资格仍以审核门槛为准。')
        with research_area('Evidence & Verification · 资料与审核概况'):
            cols = st.columns(4)
            cols[0].metric('真实平台账号记录', len(screen))
            cols[1].metric('重点研究候选', len(focus))
            cols[2].metric('已采集原帖证据', len(tables['evidence']))
            cols[3].metric('正式推荐资格', int(audit.model_eligible.sum()))
            st.subheader('研究 → 核验 → 决策')
            st.write('52 条第三方账号资料完成离线规则辅助初筛；每个平台4位重点候选。分类仅使用导出描述与定位，不使用账号名推断。重点分析为资料级研究，不代表已观看原帖。')
            st.info('当前公开网页访问未提供可可靠分析的原帖。已停止重复抓取；请在达人研究中抽查重点候选并补充最近2–3条原帖。AI建议与人工批准分别保存。')
            table(screen.groupby('platform').agg(账号数=('creator_id', 'count'), 重点候选=('focus_candidate', 'sum')).reset_index())
            st.write(f'人工待核验/待修改：{int(screen.human_status.ne("已批准").sum())}；已核验原帖：{int(tables["evidence"].verification_status.eq("verified").sum())}。')
            st.caption('四类数据：第三方报告 → 可追溯原帖 → 人工审核判断 → 独立模拟假设。原始 Excel、52条账号和历史模拟文件均保留。')
    with database:
        with research_area('完整52条数据库与12位资料分析'):
            st.subheader('52 条账号自动初筛')
            table(screen.loc[screen.platform.isin(platforms)])
            st.subheader('重点候选资料级深度分析 · 4 / 4 / 4')
            table(deep.loc[deep.platform.isin(platforms)])
        st.subheader('Priority Creators · 首批重点达人')
        priority = priority_creator_view(tables, screen, audit)
        priority = priority.loc[priority.platform.isin(platforms)]
        st.caption('每平台2位，采用已确认的首批审核名单；研究优先级不改变正式资格。基础指标均为第三方报告。')
        table(priority[['platform','handle','reported_followers','reported_mean_views','reported_median_views',
                        'reported_mean_engagement_rate','research_priority','intake_status','screening_status','research_status']])
        with st.expander('内容证据、人工审核与正式资格'):
            st.caption('“已核验”表示至少一条原帖已核验，不表示全部内容完成；二手索引仅标记线索。人工审核和正式投放门槛独立计算。')
            table(priority[['creator_id','handle','content_status','human_review_status','verified_post_count','model_eligible']])
        with st.expander('重点达人详情 · 证据来源、风险与缺失项'):
            table(priority[['creator_id','handle','evidence_basis','risks','missing_fields','exclusion_reason']])
        with research_area('Evidence & Verification · 原帖与人工审核'):
            ids = screen.loc[screen.platform.isin(platforms), 'creator_id'].tolist()
            if ids:
                display = screen.set_index('creator_id')
                creator_id = st.selectbox('抽查账号', ids, format_func=lambda cid: f'{cid} · {display.loc[cid, "platform"]} · @{display.loc[cid, "handle"]}', key='inspect_creator')
                account = tables['accounts'].set_index('creator_id', drop=False).loc[creator_id]
                st.link_button('打开原始主页', account.profile_url)
                st.write(text(account.reported_description) or 'Unknown')
                evidence = tables['evidence'].loc[tables['evidence'].creator_id.eq(creator_id)]
                if evidence.empty:
                    st.info('该账号暂无原帖证据。不能把第三方内容概述写成已核验帖子。')
                else:
                    table(evidence)
                table(tables['reviews'].loc[tables['reviews'].creator_id.eq(creator_id)])
                if not config_changed:
                    human_forms(tables, account, directory=registry_dir / 'human_reviews')
                else:
                    st.info('当前人工批准日志绑定默认演示案例；请切回默认配置审核，避免将其他产品判断混入旧日志。')
            else:
                st.info('请选择至少一个平台查看账号。')
    with recommendation:
        priority_area = st.container()
        with research_area('完整评分、权重与数据依据'):
            st.subheader('五维评分与证据覆盖')
            st.caption('缺失维度显示空白；仅在五维齐全时生成综合分。已知贡献不归一化，不作为完整排名。规则分数是透明研究工具，未经校准。')
            table(pd.DataFrame(SCORE_WEIGHTS, index=DIMENSIONS).rename_axis('评分维度').reset_index())
            columns = ['creator_id', 'handle', *DIMENSIONS, 'total_score', 'known_contribution', 'score_completeness', 'evidence_coverage', 'model_eligible']
            table(scores.loc[scores.platform.isin(platforms), columns])
            with st.expander('逐维计算依据、支持原帖与风险'):
                table(scores.loc[scores.platform.isin(platforms)])
        st.subheader('Creator Comparison · 两位达人比较')
        ids = screen.creator_id.tolist()
        display = screen.set_index('creator_id')
        selected = st.multiselect('选择两位达人', ids, default=['KOL-014','KOL-006'], max_selections=2,
            format_func=lambda cid: f'{cid} · @{display.loc[cid, "handle"]}', key='compare_creators')
        if len(selected) == 2:
            comparison_charts(tables['accounts'], scores, selected, DIMENSIONS)
            with st.expander('完整比较字段、来源与内容限制'):
                compared = scores.set_index('creator_id').loc[selected, ['handle', *DIMENSIONS, 'total_score', 'score_completeness', 'supporting_posts', 'risks', 'exclusion_reason', 'change_conditions']].T
                table(compared.map(lambda value: 'Unknown' if pd.isna(value) else str(value)).rename_axis('比较项').reset_index())
                for creator_id in selected:
                    row = display.loc[creator_id]
                    st.write(f'**{creator_id} · @{row.handle}**：{row.classification_basis}。')
                    st.caption('依据：' + row.source_reference)
                st.info('当前内容证据不足时，无法断言谁更适合正式投放。下表比较各目标的已知维度贡献，同时展示完整度；补齐真实内容与审核后才可比较完整综合分。')
            across = []
            dimension_rows = []
            for goal in SCORE_WEIGHTS:
                scored = score_registry(tables, screen, goal, score_model, fit_keyword_groups=groups)
                for row in scored.loc[scored.creator_id.isin(selected)].itertuples(index=False, name=None):
                    record = dict(zip(scored.columns, row))
                    dimension_rows.extend(dict(维度=d, 得分=record[d], 达人及目标=record['creator_id']+' · '+goal) for d in DIMENSIONS)
                subset = scored.loc[scored.creator_id.isin(selected), ['creator_id', 'total_score', 'known_contribution', 'score_completeness']].copy()
                subset['objective'] = goal
                across.append(subset)
            table(pd.concat(across, ignore_index=True))
            with st.expander('两位达人在三种目标下的分项变化 · 0–100分'):
                value_chart(pd.DataFrame(dimension_rows),'维度','得分','五维分项比较（v1；效率为Simulation）','分',group='达人及目标')
                st.caption('各维度统一0–100分；缺失项不绘柱，不按零分参与比较。目标变化可能只改变效率分和加权贡献。')
        else:
            st.info('请选择两位达人进行比较。')
        st.subheader('预算组合 · ' + mode)
        if result.selected.empty:
            st.info('当前没有可行组合。正式池为空时应先完成审核；演练池为空时检查平台、预算或效果假设。')
        else:
            table(result.selected[['creator_id', 'creator_name', 'platform', 'estimated_fee_usd', 'execution_cost_usd', 'target_reach', 'projected_engagements', 'projected_clicks', 'projected_conversions']])
        render_metrics(result.metrics, METRICS)
        st.caption('复用 portfolio.py 精确0/1背包，以当前目标的累计模拟效果最大化，最多6人；五维研究评分帮助解释内容与证据，不替代组合目标函数。')
        st.subheader('为什么入选、为什么未入选、哪些条件会改变选择')
        with st.expander('推荐决策视图 · Simulation选择与正式资格分开'):
            if not result.candidates.empty:
                plotted = result.candidates.copy()
                plotted['组合状态'] = plotted.creator_id.map(lambda cid: '入选（模拟）' if cid in set(result.selected.creator_id) else '未入选')
                value_chart(plotted,'creator_id',{'Brand Awareness':'target_reach','Engagement':'projected_engagements','Conversion':'projected_conversions'}[objective],
                            '候选达人模拟目标贡献 · '+objective,{'Brand Awareness':'触达人次（未去重）','Engagement':'互动次数','Conversion':'转化期望数'}[objective],group='组合状态',horizontal=True)
            categories = explanations.groupby('status').size().rename('人数').reset_index()
            value_chart(categories,'status','人数','当前组合选择/排除原因','人数',horizontal=True)
            st.caption('资格不足不等于内容不匹配；模拟入选账号也可能尚未获得正式资格。具体依据与改变条件仍见下表。')
        decision_summary(explanations, result)
    with scenarios:
        st.subheader('统一情景对比')
        st.caption('固定基准：$5,000 · Brand Awareness · Base（CTR 1%、CVR 2%）。使用当前计算范围及平台；不受左侧当前预算和目标影响。')
        suite = cached_suite(model)
        for family in ('预算变化', '目标变化', '效果假设'):
            st.write('**' + family + '**')
            table(suite.loc[suite.family.eq(family)])
        with st.expander('营销目标与效果假设 · 可视化 Simulation'):
            goals = suite.loc[suite.family.eq('目标变化')]
            weights = pd.DataFrame(SCORE_WEIGHTS,index=DIMENSIONS).rename_axis('评分维度').reset_index().melt(id_vars='评分维度',var_name='营销目标',value_name='权重')
            value_chart(weights,'评分维度','权重','三种营销目标的评分权重（v1）','权重（0–1）',group='营销目标')
            outcome_charts(goals,'objective','三种营销目标的组合预测')
            matrix = pd.DataFrame([dict(目标=r.objective, 达人=cid, 状态='入选（模拟）') for r in goals.itertuples() for cid in r.selected_ids.split(', ') if cid != '无'])
            if not matrix.empty:
                st.markdown('**营销目标 × 达人组合矩阵（Simulation）**')
                st.vega_lite_chart(matrix, {'mark':'rect','height':max(260,matrix['达人'].nunique()*32),'padding':{'top':20,'bottom':20,'left':20,'right':20},
                    'encoding':{'x':{'field':'目标','type':'nominal'},'y':{'field':'达人','type':'nominal'},
                    'color':{'field':'状态','type':'nominal','legend':{'orient':'bottom'},'scale':{'range':CHART_COLORS}},'tooltip':[{'field':'目标'},{'field':'达人'},{'field':'状态'}]}},width='stretch')
            st.caption('同名单也是优化结果；矩阵展示各目标实际入选者，进入/退出名单及权重见原有对照表。')
            assumptions = suite.loc[suite.family.eq('效果假设')]
            value_chart(assumptions,'scenario','clicks','Simulation · 效果假设与点击','点击（次）',group='calculation',line=True)
            value_chart(assumptions,'scenario','conversions','Simulation · 效果假设与转化','转化（期望数）',group='calculation',line=True)
            rates = assumptions.loc[assumptions.calculation.eq('重新优化')].copy()
            rates['CTR（%）'], rates['CVR（%）'] = rates.assumed_ctr*100, rates.assumed_cvr*100
            rate_data = rates.melt(id_vars=['scenario'],value_vars=['CTR（%）','CVR（%）'],var_name='模拟参数',value_name='百分比')
            value_chart(rate_data,'scenario','百分比','CTR / CVR模拟假设','%',group='模拟参数',line=True)
            st.caption('固定组合与重新优化曲线可能重合，不人为错开数值；所有转化均为模拟期望。')
        st.caption('Conservative：CTR 0.5%、CVR 1%；Base：1%、2%；Optimistic：1.5%、3%。所有效果均为模拟；固定组合与重新优化均实际计算。')
        st.info('共同 CTR/CVR 只按比例缩放每人的点击/转化时，最优组合可能保持不变。Awareness 与 Conversion 在共同转化率下也可能同名单；不会人为制造名单变化。')
        with st.expander('查看预算/目标情景的逐账号淘汰理由'):
            family = st.selectbox('解释情景类型', ['预算变化', '目标变化'], key='reason_family')
            if family == '预算变化':
                comparison_budget = st.selectbox('解释预算', [3000, 5000, 8000])
                goal = 'Brand Awareness'
            else:
                comparison_budget = 5000
                goal = st.selectbox('解释营销目标', list(SCORE_WEIGHTS))
            plan = run_plan(model, comparison_budget, goal, ctr=.01, cvr=.02)
            decision_summary(selection_explanations(tables, screen, plan, goal), plan)
        st.subheader('What-if · 单人报价、预算及效果假设')
        if model.empty:
            st.info('当前计算范围没有候选。请先审核正式候选，或切换研究情景演练。')
        else:
            creator_id = st.selectbox('修改模拟报价的达人', model.creator_id.tolist(), key='whatif_creator')
            fee = float(model.set_index('creator_id').loc[creator_id, 'estimated_fee_usd'])
            # Key by creator to avoid carrying another creator’s edited fee to a new selection.
            new_fee = st.number_input('新模拟报价（美元）', min_value=1., max_value=1000000., value=fee, step=50., key='whatif_fee_' + creator_id)
            new_budget = st.number_input('What-if 预算（美元）', min_value=0, max_value=10000, value=5000, step=100, key='whatif_budget')
            new_goal = st.selectbox('What-if 营销目标', list(SCORE_WEIGHTS), key='whatif_goal')
            new_ctr = st.number_input('What-if CTR（%）', min_value=0., max_value=100., value=1., step=.1, key='whatif_ctr') / 100
            new_cvr = st.number_input('What-if CVR（%）', min_value=0., max_value=100., value=2., step=.1, key='whatif_cvr') / 100
            changed = run_plan(model, new_budget, new_goal, new_ctr, new_cvr, {creator_id: new_fee})
            baseline = run_plan(model, 5000, 'Brand Awareness', .01, .02)
            base_ids, ids = set(baseline.selected.get('creator_id', [])), set(changed.selected.get('creator_id', []))
            st.write('相对固定基准进入：' + ('、'.join(sorted(ids - base_ids)) or '无') + '；退出：' + ('、'.join(sorted(base_ids - ids)) or '无'))
            if ids == base_ids:
                st.caption('本次输入没有改变最优名单；请比较支出与预测指标，名单不变也是有效结论。')
            with st.expander('What-if前后效果图 · Simulation'):
                portfolio_change_charts(baseline,changed,'报价/预算/目标调整前后')
            table(pd.DataFrame([dict(方案='固定基准', **baseline.metrics), dict(方案='What-if', **changed.metrics)]))
            decision_summary(selection_explanations(tables, screen, changed, new_goal), changed)
    with report:
        st.subheader('当前结果与可追溯研究导出')
        st.write(f'资料初筛 {len(screen)} 条；重点资料分析 {len(deep)} 条；本次自动采集并分析原帖 0 条；人工新增证据 {len(tables["evidence"])} 条；正式资格 {int(audit.model_eligible.sum())} 条。')
        st.caption('工作台不使用付费API。初筛和资料分析为本地透明规则；源材料不足时不会生成事实性内容结论。')
        downloads = [('下载52条研究初筛 CSV', screen, 'creator_screening.csv'),
                     ('下载12位重点研究与待核验清单 CSV', deep, 'focus_research.csv'),
                     ('下载五维评分与解释 CSV', scores, 'creator_scores.csv'),
                     ('下载情景对比 CSV', suite.assign(planning_mode=mode, model_data_type='simulated'), 'scenario_comparison.csv'),
                     ('下载淘汰与资格原因 CSV', explanations, 'selection_reasons.csv'),
                     ('下载当前原帖证据 CSV', tables['evidence'], 'content_evidence.csv'),
                     ('下载当前人工审核 CSV', tables['reviews'], 'human_reviews.csv'),
                     ('下载独立模拟参数 CSV', sandbox_assumptions(tables['accounts'], screen) if sandbox else tables['assumptions'], 'planning_assumptions.csv')]
        for label, frame, filename in downloads:
            st.download_button(label, safe_csv(frame.assign(campaign_config=json.dumps(campaign, ensure_ascii=False))), file_name=filename, mime='text/csv')
        if not result.selected.empty:
            st.download_button('下载当前模拟组合 CSV', export_portfolio_csv(result,
                dict(**{k: str(v) for k,v in campaign.items()}, planning_mode=mode, budget_usd=budget, objective=objective, assumed_ctr=ctr, assumed_cvr=cvr,
                     source='third-party reports; original provenance retained in research exports', formal_eligible_count=int(audit.model_eligible.sum()))),
                file_name='registry_simulated_portfolio.csv', mime='text/csv')
        with st.expander('计算公式与演示边界'):
            st.write('模拟调整触达＝独立假设触达×模拟受众调整参数÷100；互动＝调整触达×模拟互动率；点击＝调整触达×CTR；转化＝点击×CVR。CPM/CPE/CPC/CPA＝支出÷相应效果（CPM×1000），分母0时不适用。')
            st.write('预算效率评分使用当前目标模拟效果÷报价÷固定目标上限×100，封顶100。旧优化器的质量兼容参数仅为模拟输入，独立于真实内容适配评分。场景报价不代表真实市场报价；播放不是触达，地区不是受众。')
            st.write('未完成：可靠的近期原帖采集、人工身份与内容审核、独立受众证据及真实报价。当前不能声称已完成真实内容适配验证或正式投放推荐。')
    from campaign_upgrade_ui import render_upgrade
    render_upgrade(tables, screen, score_model, result, objective, budget, mode, database, recommendation, scenarios, report, campaign=campaign, supplement_path=registry_dir / 'hicreator_supplement.csv', priority_area=priority_area)
    with report:
        st.download_button('下载当前Campaign配置', json.dumps(dict(campaign, budget_usd=budget, objective=objective), ensure_ascii=False, indent=2), file_name='campaign_config.json')
    st.divider()
    st.caption('独立演示项目；默认PETKIT案例无品牌隶属或背书关系。' + NOTICE)
