"""简体中文展示层：不改原始资料、内部标识或计算输入。"""
import re

import pandas as pd
import streamlit as st

LABELS = {
    "Budget": "预算", "cost": "费用", "Creator fee": "创作者报价", "Sample cost": "样品成本", "Shipping cost": "物流成本",
    "Simulated Demo Dataset": "模拟演示数据集", "Real Creator Research Dataset": "真实创作者研究数据集",
    "Brand Awareness": "品牌认知", "Engagement": "互动提升", "Conversion": "转化提升",
    "audience": "受众匹配", "reach": "触达", "engagement": "互动", "quality": "内容质量", "efficiency": "成本效率",
    "creator_id": "创作者编号", "creator_name": "创作者名称", "handle": "公开账号名", "platform": "平台",
    "creator_category": "内容分类", "followers": "粉丝数（有日期的观测）", "creators": "创作者数量",
    "profile_url": "公开主页", "source_url": "资料来源", "source_data_date": "来源日期", "source_date_basis": "来源日期口径",
    "follower_count_checked_at": "粉丝数核验日期", "reported_followers": "第三方近似粉丝数", "follower_count_notes": "粉丝数说明",
    "recent_post_url": "近期原帖链接", "recent_post_date": "近期内容日期", "recent_content_source_url": "第三方内容记录",
    "visible_likes": "可见点赞数", "visible_comments": "可见评论数", "visible_views": "历史可见播放量",
    "observed_engagement_rate": "公开观测互动率", "engagement_rate_basis": "观测互动率口径",
    "us_audience_share": "美国受众比例（第三方估计）", "us_audience_evidence": "美国受众证据",
    "petkit_collaboration_evidence": "PETKIT 历史合作线索", "competitor_collaboration_evidence": "竞品合作线索",
    "verification_status": "核验状态", "verification_tier": "研究层级", "manual_review_fields": "待人工复核项",
    "notes": "核验说明", "research_checked_at": "研究核验日期", "identity_data_type": "身份资料类型",
    "fit_rationale": "产品适配理由（研究判断）", "fit_assessment_type": "适配评价类型",
    "model_enabled": "是否启用建模", "model_eligible": "参数是否完整有效", "model_eligibility_reason": "建模资格说明",
    "model_data_type": "模型数据类型", "numeric_score_basis": "数值评分依据", "data_type": "数据性质",
    "assumption_version": "假设版本", "planning_basis": "模拟参数配置依据", "exclusion_reason": "暂缓建模原因",
    "estimated_fee_usd": "模拟合作报价（美元）", "estimated_reach": "模拟单条触达量",
    "engagement_rate": "模型互动率（模拟比率）", "audience_match_score": "受众匹配分（模拟）",
    "content_quality_score": "内容质量分（模拟）", "total_score": "综合评分（满分 100）",
    "assumed_engagement_rate": "模型互动率假设", "assumed_ctr": "点击率假设（CTR）",
    "assumed_cvr": "转化率假设（CVR）", "assumed_click_to_purchase_cvr": "点击后购买转化率假设（CVR）",
    "assumed_audience_match_score": "受众匹配分预设", "assumed_content_quality_score": "内容质量分预设",
    "execution_cost_usd": "单人执行成本（美元）", "raw_reach": "累计内容触达（未去重）",
    "target_reach": "受众调整触达量（未去重）", "projected_engagements": "预估互动量",
    "projected_clicks": "预估点击量", "projected_conversions": "预估转化量",
    "recommendation_reason": "排序参考理由", "selection_reason": "组合入选理由",
    "metric": "指标", "baseline": "基准方案", "current": "当前方案", "absolute_change": "绝对变化", "percent_change": "变化比例（%）",
    "brand": "品牌", "product": "产品", "market": "目标市场", "objective": "营销目标", "budget_usd": "总预算（美元）",
    "sample_usd": "每人样品成本（美元）", "shipping_usd": "每人物流成本（美元）", "max_creators": "人数上限",
    "platforms": "平台筛选", "categories": "分类筛选", "min_followers": "最低粉丝数", "min_engagement_pct": "最低互动率（%）",
    "min_match": "最低匹配分", "max_fee": "最高模拟报价（美元）", "min_quality": "最低质量分",
    "budget_only": "仅保留报价在单人预算内的候选", "dataset": "数据集",
    "partially_verified": "部分核实", "unverified": "未核实", "simulated": "模拟数据",
    "public_profile": "公开账号身份", "researcher_interpretation": "研究者判断", "simulated_preset": "模拟预设",
    "hybrid_public_identity_simulated_model": "真实公开身份＋模拟投放模型",
    "Cat creators": "猫咪创作者", "Pet lifestyle": "宠物生活", "Pet product reviews": "宠物产品测评", "Smart home": "智能家居",
    "Pet product experience": "宠物产品体验", "Cat lifestyle": "猫咪生活", "Cat care": "猫咪照护", "Multi-cat care": "多猫照护",
    "Multi-pet product experience": "多宠产品体验", "Cat lifestyle / product experience": "猫咪生活／产品体验",
    "Multi-cat household": "多猫家庭", "Multi-cat / pet technology": "多猫家庭／宠物科技", "Family / pet lifestyle": "家庭／宠物生活",
    "Cat lifestyle / pet technology": "猫咪生活／宠物科技", "Rescue pets / product experience": "宠物救助／产品体验",
    "Cats / home / pet technology": "猫咪／家居／宠物科技", "Multi-cat product experience": "多猫产品体验",
    "Two-cat lifestyle": "双猫生活", "Cat lifestyle / care": "猫咪生活／照护", "Pet product experience / UGC": "宠物产品体验／用户创作内容",
    "Cat behavior / care": "猫行为／照护", "Cat / family lifestyle": "猫咪／家庭生活", "Home / multi-pet lifestyle": "家居／多宠生活",
    "Cat lifestyle / outdoors": "猫咪生活／户外", "Multi-pet lifestyle / DIY": "多宠生活／手作",
    "General / pet product experience": "综合产品／宠物用品体验", "Family / pet supplies": "家庭／宠物用品",
}

# 仅翻译已批准资料的说明；原始 CSV 保留英文，来源地址不变。
FIT_ZH = dict(zip([f"REAL{i:03}" for i in range(1, 31)], [
    "公开资料介绍产品测试与用户创作内容；喂食器内容可形成使用场景。",
    "历史喂食器、饮水机内容与产品演示相关。",
    "猫咪生活及历史 PETKIT 产品内容不能证明未来投放表现。",
    "照护、喂食习惯适合解释使用场景；硬件测评能力未核实。",
    "有多猫救助与照护场景；硬件适用性仍需复核。",
    "有猫咪生活及历史宠物设备内容线索。",
    "多宠饮水机内容可提供家庭演示场景；猫咪内容占比未核实。",
    "有喂食及设备体验线索；英国创作者仅作有条件的跨市场备选。",
    "多猫家庭及获赠饮水机的记录提供了相关场景。",
    "有饮水机和宠物设备内容；美国受众是否占多数尚未核实。",
    "创作者链接页列有 PETKIT 饮水机和 PETLIBRO 喂食器，具备设备演示场景线索。",
    "有历史喂食器介绍；是否持续创作猫咪内容仍需核实。",
    "历史双粮仓喂食器内容与默认案例直接相关。",
    "历史喂食器、饮水机内容相关；竞品关系待复核。",
    "有猫咪照护与设备体验线索；猫咪内容占比需复核。",
    "多猫简介及智能猫砂盆内容与家庭设备场景相关。",
    "家居、猫咪设备内容可提供室内产品故事。",
    "有历史射频识别喂食器、饮水机内容；近期活跃度未核实。",
    "双猫生活可形成喂食场景；硬件演示能力未核实。",
    "具有猫咪照护场景；简介是兽医的猫，不代表已核实专业资格。",
    "有产品分享、用户创作内容线索；已有内容证据不在近期窗口内。",
    "双猫生活可支持喂食故事；设备体验尚未确认。",
    "可探索喂食习惯解释；专业资格未核实。",
    "简介描述猫主人生活；设备适配仅为研究判断。",
    "简介描述两猫一犬，可探索家居摆放故事；并非已核实的科技测评账号。",
    "猫咪生活备选，室内喂食器适配较间接，研究优先级较低。",
    "有多猫照护场景；特殊需要猫咪的设备适用性须人工评估。",
    "有多宠家庭场景；喂食设备体验尚未确认。",
    "有历史猫咪用品体验；宠物内容占比及硬件能力需复核。",
    "有猫主人及宠物用品内容；喂食器适配和活跃度核实前优先级较低。",
]))
PETKIT_ZH = {
    "REAL001": "报告记录 2026-02-13 的 YumShare 内容及创作者自述的 PETKIT 经历；并非已核实合同。",
    "REAL002": "报告记录历史 YumShare 和饮水机内容，含 2026-04-16 的广告披露；不代表当前合同。",
    "REAL003": "报告记录历史 PETKIT 产品内容；不代表当前可合作或已验证效果。",
    "REAL006": "报告记录历史 PETKIT 宠物设备内容；当前关系未核实。",
    "REAL007": "第三方目录记录 2026-06-11 的 PETKIT 饮水机内容；并非当前合同证明。",
    "REAL009": "第三方目录记录 2026-05-28 的内容，提到获赠 PETKIT 饮水机。",
    "REAL010": "报告记录历史 PETKIT 饮水机内容；持续合作关系未核实。",
    "REAL011": "创作者链接页列有 PETKIT 饮水机；产品链接不能证明付费合同。",
    "REAL012": "第三方索引记录 2026-02-23 的智能喂食器介绍。",
    "REAL013": "第三方索引记录 2026-03-03 的双粮仓喂食器内容；原帖未直接核验。",
    "REAL014": "报告记录历史 PETKIT 喂食器、饮水机内容。",
}
COMPETITOR_ZH = {
    "REAL001": "创作者商业档案自述 CATLINK 经历；日期、条款未核实。",
    "REAL005": "创作者链接页列有 PETLIBRO 产品；当前合同、排他约定未核实。https://linktr.ee/heidiwranglescats",
    "REAL006": "有历史 SiiPet 设备内容线索；日期、条款待复核。",
    "REAL008": "有历史 Cheerble 等设备体验线索；日期、条款待复核。https://www.modash.io/content-library/brands/cheerble-examples/influencers",
    "REAL010": "有历史 Cheerble 内容；当前条款未核实。",
    "REAL011": "创作者页面列有 PETLIBRO 喂食器等设备；并非付费合同证明。",
    "REAL014": "有历史 PetSafe 内容；当前条款未核实。https://www.modash.io/content-library/brands/petsafe-examples",
    "REAL015": "PETLIBRO 内容记录日期为 2026-10-03；合作条款未核实。",
    "REAL016": "PETLIBRO 智能猫砂盆内容记录日期为 2026-09-24；条款未核实。",
    "REAL017": "PETLIBRO 内容记录包含 2026-08-25；交付形式、条款未核实。",
    "REAL018": "有历史 PETLIBRO 射频识别喂食器、饮水机内容；近期关系未知。",
}
TEXT = {
    "Date not established in approved report": "已批准报告未能确定日期",
    "Specific third-party historical table row dated 2026-10-17": "第三方历史表中日期为 2026-10-17 的具体记录",
    "Source page date only; individual measurement date undisclosed": "仅为来源页面日期，未披露单项测量日期",
    "Unknown; do not impute zero or copy another platform count.": "未知，不填 0，也不复制其他平台的粉丝数。",
    "Third-party historical snapshot, not a live platform observation. Previous 2026-10-23 figure is not reused.": "第三方历史快照，并非平台实时观测；未沿用之前 2026-10-23 的不同数值。",
    "Approximate third-party page figure retained only in reported_followers. Page date is not an individual measurement date; followers stays blank.": "第三方页面近似数仅保留在 reported_followers；页面日期不等于单项测量日，followers 留空。",
    "Not calculated: denominator, sample size and observation window unavailable.": "未计算：缺少分母、样本量及统计窗口。",
    "Unverified; location, language and country rank are not audience-share evidence.": "未核实；所在地、语言、国家排名不能作为受众比例证据。",
    "Unverified: conflicting public commercial estimates; UK creator location does not determine audience geography.": "未核实：公开商业估计有冲突；英国所在地不能决定受众地域。",
    "Current profile and activity; follower measurement date; original post URL and metrics; US audience; current brand relationships and booking readiness": "当前主页与活跃度、粉丝测量日期、原帖链接及指标、美国受众、当前品牌关系及实际合作条件",
    "Transcribed from approved conversation report, not a fresh platform verification.": "根据已批准的会话报告转录，并非重新进行平台核验。",
    "Blank collaboration evidence means not verified, not no collaboration.": "合作证据空白表示未核实，不表示从未合作。",
    "Recent date comes from a third-party content record/search index. Original recent_post_url remains blank; no invented permalink. Counts, when supplied, belong to that record only.": "近期日期来自第三方内容记录或搜索索引；未获得原帖链接，不补造地址。已有计数仅属于对应记录。",
    "UK-based conditional alternative; do not assert US-majority audience. Conflicting follower figures excluded.": "英国创作者仅作有条件的备选，不断言美国受众占多数；已排除相互冲突的粉丝数。",
    "Illustrative standard feeder/device-content scenario based on a historical content/link signal in the approved report. All numeric values are independent authored presets, not individual performance estimates.": "基于已批准报告中的历史喂食器或设备内容线索配置标准演示场景；所有数值均为独立编写的预设，并非个人表现估计。",
    "No authored feeder-planning template for this candidate. Manually review product fit, recent activity and campaign assumptions before enabling; no automatic parameter fill.": "尚未为该候选配置喂食器投放模板；启用前须人工核实产品适配、近期活跃度和假设，不自动补齐参数。",
    "Author-set $500 scenario placeholder per short video; not creator quote or market rate.": "每条短视频 $500 为人为设定的场景占位值，并非创作者报价或市场价格。",
    "Author-set 20000 non-deduplicated content reach; not historical views, follower-derived estimate or verified forecast.": "20,000 次未去重内容触达为人为预设，不是历史播放量、粉丝推算值或已验证预测。",
    "Author-set 0.05 simulated interactions / target reach; not observed ER.": "互动率 0.05 为人为模拟预设，分母为受众调整触达，不是观测互动率。",
    "Author-set 0.02 simulated clicks / target reach; not observed CTR.": "点击率 0.02 为人为模拟预设，分母为受众调整触达，不是观测 CTR。",
    "Author-set 0.02 simulated conversions / clicks; not observed purchase rate.": "转化率 0.02 为人为模拟预设，分母为点击，不是观测购买率。",
    "Author-set neutral demonstration preset 70/100; not US audience share or measured fit.": "70/100 为演示匹配分预设，不是美国受众比例或实际测量的匹配度。",
    "Author-set demonstration preset 70/100; not a review of creator videos.": "70/100 为演示质量分预设，不代表已审核创作者视频。",
    "Model inputs complete; SIMULATED planning only. Booking and US audience remain unverified.": "模型输入完整，仅用于模拟规划；实际合作条件及美国受众仍未核实。",
    "Model disabled or no assumption row; ": "未启用建模或缺少假设记录；",
    "parameters require explicit configuration": "需要明确配置参数",
    "Missing parameter source: ": "缺少参数来源：", "Missing ": "缺少参数：", "Invalid ": "参数无效：",
    "Model provenance/version is invalid": "模型来源或版本无效", "Planning basis is missing": "缺少参数配置依据",
    "No feasible positive-outcome portfolio: check filters, budget and per-creator execution costs.": "没有可行且模拟效果大于零的组合，请检查筛选条件、预算及单人执行成本。",
    "Data or model assumptions changed. Save a new baseline before comparing.": "数据或模型假设已变化，请重新保存基准方案后再比较。",
    "Portfolio exceeds the campaign budget.": "组合支出超过活动预算。",
    "Demo budget must not exceed $10,000.": "演示预算不得超过 $10,000。",
    "Maximum creators must be an integer from 1 to 6.": "人数上限必须为 1 至 6 的整数。",
    "This demo supports at most 30 candidate creators.": "本演示最多支持 30 个候选创作者。",
    "No recommended creators to export.": "当前没有可导出的推荐创作者。",
    "KOL data is empty; at least one creator is required.": "创作者数据为空，至少需要一条记录。",
    "creator_id must be unique.": "创作者编号 creator_id 必须唯一。",
    "Research/assumption CSV is empty.": "研究资料或假设 CSV 为空。",
    "Research/assumption creator_id must be non-blank and unique.": "研究资料和假设表中的创作者编号不得为空或重复。",
    "Simulated planning parameters must not be stored in the public research table.": "模拟投放参数不得存入公开研究资料表。",
    "Research identity_data_type must be public_profile.": "研究身份类型必须为公开账号资料。",
    "This approved report does not establish any fully verified creators.": "已批准报告未确认任何完全核验的创作者，不得标为完全验证。",
    "verification_tier must be A or B.": "研究层级必须为 A 或 B。",
    "Fit rationale is a researcher interpretation, not an observed fact.": "适配理由必须标为研究者判断，不能标为公开观测事实。",
    "Observed followers require a source date and checked date.": "观测粉丝数必须具有来源日期和核验日期。",
    "Observed engagement requires denominator, sample and time-window evidence.": "观测互动率必须有分母、样本及统计窗口说明。",
    "US audience estimates require evidence.": "美国受众比例估计必须具有证据来源。",
    "model_enabled must be true or false.": "建模启用标记必须为 true 或 false。",
    "All campaign assumptions must be labeled simulated.": "所有投放假设必须标为模拟数据。",
    "Unexpected research planning assumption version.": "研究规划假设版本与程序预期不一致。",
    "Join requires unique creator_id in both tables.": "关联时，两张表的创作者编号都必须唯一。",
    "data_type must be simulated or hybrid_public_identity_simulated_model.": "数据性质标记必须为纯模拟，或真实公开身份与模拟模型的混合类型。",
}

DISCLAIMER_ZH = "报价、效果预测及数值匹配分、质量分均为模拟预设。演示数据集的身份为虚构，研究数据集使用公开账号身份；部分核实不代表可实际投放。美国宠物科技匹配仅为简化假设。累计触达未去重；转化为数学期望，不是真实订单或投资回报。每人按一条短视频建模，费用含合作费及假设的样品、物流，不含税、内部人力和付费放大。未连接真实 AI 接口。"


def label(value):
    return LABELS.get(value, value)


def column_label(field):
    if field in LABELS:
        return LABELS[field]
    for suffix, ending in (("_source", "：来源说明"), ("_contribution", "：加权贡献"), ("_score", "：分项得分")):
        if field.endswith(suffix):
            return column_label(field[:-len(suffix)]) + ending
    return field  # 未知技术字段保留，避免改变数据含义。


def text_zh(value):
    if not isinstance(value, str):
        return value
    if value in LABELS:
        return LABELS[value]
    if value in TEXT:
        return TEXT[value]
    if value.startswith("Third-party estimate, NOT creator backend data. Source: "):
        return value.replace("Third-party estimate, NOT creator backend data. Source: ", "第三方估计，并非创作者后台数据。来源：").replace("; source page date: ", "；来源页面日期：")
    result = value
    for name in ("Budget", "Creator fee", "Sample cost", "Shipping cost"):
        if result.startswith(name + " must be "):
            result = label(name) + result[len(name):]
    for original, translated in TEXT.items():
        if original in ("Missing ", "Invalid "):
            continue  # 先匹配完整错误模板，再处理通用前缀。
        if original in result:
            result = result.replace(original, translated)
    for pattern, replacement in (
        (r"Excluded (\d+) invalid or duplicate creator records\.", r"已排除 \1 条无效或编号重复的创作者记录。"),
        (r"Unknown campaign objective: (.*)", lambda m: "未知营销目标：" + str(label(m[1]))),
        (r"Missing required fields: (.*)", r"缺少必要字段：\1"),
        (r"Missing research/assumption fields: (.*)", r"研究资料或假设表缺少字段：\1"),
        (r"Unable to read KOL CSV: (.*)", r"无法读取创作者 CSV：\1"),
        (r"Unable to read research/assumption CSV: (.*)", r"无法读取研究资料或假设 CSV：\1"),
        (r"(.+) must contain finite numbers between (.+) and (.+)\.", r"字段 \1 必须为 \2 至 \3 之间的有限数值。"),
        (r"(.+) must contain whole numbers\.", r"字段 \1 必须为整数。"),
        (r"(.+) must not contain missing or blank values\.", r"字段 \1 不得有缺失值或空白。"),
        (r"(.+) must be a finite non-negative USD amount with at most two decimal places\.", r"\1 必须为有限、非负且最多两位小数的美元金额。"),
        (r"Public research (.+) must not be blank\.", r"公开研究字段 \1 不得为空。"),
        (r"Invalid public research numeric field: (.+)", r"公开研究数值字段无效：\1"),
        (r"Assumptions reference unknown creator_id: (.+)", r"假设表引用了未知的创作者编号：\1"),
        (r"Hybrid records require (.+)", r"混合数据记录缺少必要来源标记：\1"),
        (r"Simulated assumption_version must be (.+)\.", r"模拟数据的假设版本必须为 \1。"),
        (r"Hybrid assumption_version must be (.+)\.", r"混合数据的假设版本必须为 \1。"),
    ):
        result = re.sub(pattern, replacement, result)
    for prefix in ("Missing ", "Invalid "):
        result = result.replace(prefix, TEXT[prefix])
    return result


def creator_reason_zh(row):
    if row.get("identity_data_type") == "public_profile":
        return (f"公开研究：{row['handle']}（{row['platform']}），核验状态为{label(row['verification_status'])}。"
                f"研究判断：{FIT_ZH.get(row['creator_id'], text_zh(row['fit_rationale']))}"
                f"模拟模型：匹配分 {row['audience_match_score']:.0f}/100，质量分 {row['content_quality_score']:.0f}/100，"
                f"以触达为分母的互动率 {row['engagement_rate']:.1%}，报价 ${row['estimated_fee_usd']:,.0f}。仅作规划演示，不代表实际表现或可预订。")
    return (f"模拟受众匹配 {row['audience_match_score']:.0f}/100；内容质量 {row['content_quality_score']:.0f}/100；"
            f"互动率 {row['engagement_rate']:.1%}；报价 ${row['estimated_fee_usd']:,.0f}。仅为单人排序参考，组合适配另行计算。")


def selection_reason_zh(row):
    return (f"组合选择（模拟）：在预算与人数约束下，作为目标效果最大的组合成员入选；执行成本 "
            f"${row['execution_cost_usd']:,.2f}，单人评分 {row['total_score']:.2f}/100。入选来自组合比较，不是按单人评分顺序选择。")


def display_frame(data):
    """只创建展示副本；不回写身份、模拟参数或评分结果。"""
    result = data.copy(deep=True)
    for field in result.select_dtypes(include=["str", "object", "bool"]).columns:
        if field in ("creator_name", "creator_id", "handle") or field.endswith("_url"):
            continue
        result[field] = result[field].map(lambda v: ("是" if v else "否") if isinstance(v, bool) else text_zh(v))
    if "creator_id" in result:
        for field, translations in (("fit_rationale", FIT_ZH), ("petkit_collaboration_evidence", PETKIT_ZH), ("competitor_collaboration_evidence", COMPETITOR_ZH)):
            if field in result:
                result[field] = [translations.get(identity, text_zh(value)) for identity, value in zip(data.creator_id, data[field])]
    if "verification_tier" in result:
        result["verification_tier"] = result.verification_tier.map({"A": "A：基础研究", "B": "B：深度研究（部分核实）"})
    if "recommendation_reason" in result:
        result["recommendation_reason"] = data.apply(creator_reason_zh, axis=1)
    if "selection_reason" in result:
        result["selection_reason"] = data.apply(selection_reason_zh, axis=1)
    return result


def show_table(data, **kwargs):
    config = {field: column_label(field) for field in data.columns}
    config.update(kwargs.pop("column_config", {}))
    return st.dataframe(display_frame(data), column_config=config, **kwargs)


def campaign_zh(campaign):
    result = {}
    for key, value in campaign.items():
        if isinstance(value, str):
            value = "、".join(str(label(item.strip())) for item in value.split(", "))
        elif isinstance(value, bool):
            value = "是" if value else "否"
        result[column_label(key)] = value
    return result
