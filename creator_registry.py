"""Stage A: independent platform-account registry; no scoring or forecasting.

Import the approved XLSX with Python's standard library. Account IDs are read
from XML as text, including numeric cells whose original precision is unsafe.
The existing Streamlit application does not consume these files yet.
"""
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import date
from hashlib import sha256
from urllib.parse import urlparse
import csv
import math
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / 'data' / 'PETKIT_三平台真实达人数据库_20261030.xlsx'
REGISTRY_DIR = ROOT / 'data' / 'creator_registry'
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
PLATFORMS = {'Instagram', 'TikTok', 'YouTube'}
FIELD_MAP = {
    '记录ID': 'creator_id', '平台': 'platform', '用户名': 'handle',
    '达人名称': 'creator_name', '主页链接': 'profile_url', '备用主页链接': 'alternate_profile_url',
    '账号ID': 'platform_account_id', '达人描述（HiCreator导出）': 'reported_description',
    '达人定位（HiCreator导出）': 'reported_position', '粉丝数/订阅数': 'reported_followers',
    '创作者地区': 'creator_region', '语言': 'reported_language',
    '中位播放量': 'reported_median_views', '平均播放量': 'reported_mean_views',
    '平均互动率': 'reported_mean_engagement_rate', '中位互动率': 'reported_median_engagement_rate',
    '数据核验状态': 'source_verification_status', '数据来源': 'data_source',
    '采集日期': 'export_date', '来源文件': 'source_file',
    '同名跨平台待核对': 'cross_platform_name_hint', '主页链接重复标记': 'source_duplicate_url_hint',
}
ACCOUNT_FIELDS = (*FIELD_MAP.values(), 'account_id_source_cell_type', 'account_id_precision_status',
    'verified_platform_account_id', 'metric_data_date', 'metric_basis', 'source_date_basis',
    'identity_data_type', 'source_workbook', 'source_sheet', 'source_row', 'source_workbook_sha256',
    'entity_id', 'entity_link_status', 'entity_link_evidence', 'entity_link_checked_by',
    'entity_link_checked_at', 'subject_type_hint', 'confirmed_subject_type',
    'us_audience_share', 'us_audience_evidence', 'content_format')
STAGES = ('identity', 'content', 'fit', 'subject_type', 'model')
REVIEW_FIELDS = ('creator_id', *(f'{stage}_{suffix}' for stage in STAGES
    for suffix in ('status', 'reason', 'checked_by', 'checked_at')))
EVIDENCE_FIELDS = ('evidence_id', 'creator_id', 'platform', 'post_url', 'post_date',
    'content_format', 'content_topic', 'visible_views', 'visible_likes', 'visible_comments',
    'evidence_source', 'checked_at', 'verification_status', 'product_relevance_reason')
PARAMETERS = ('estimated_fee_usd', 'estimated_reach', 'assumed_engagement_rate',
    'assumed_ctr', 'assumed_cvr', 'assumed_audience_match_score', 'assumed_content_quality_score')
ASSUMPTION_FIELDS = ('creator_id', 'platform', 'content_format', 'model_data_type',
    'assumption_version', 'assumption_status', 'planning_basis', 'engagement_rate_basis',
    *PARAMETERS, *(f'{p}_source' for p in PARAMETERS), 'checked_by', 'checked_at')
NUMERIC_ACCOUNT_FIELDS = ('reported_followers', 'reported_median_views', 'reported_mean_views',
    'reported_mean_engagement_rate', 'reported_median_engagement_rate', 'us_audience_share')
FILES = {'accounts': ('accounts.csv', ACCOUNT_FIELDS), 'reviews': ('reviews.csv', REVIEW_FIELDS),
         'evidence': ('content_evidence.csv', EVIDENCE_FIELDS),
         'assumptions': ('campaign_assumptions.csv', ASSUMPTION_FIELDS)}


def read_source_workbook(path=SOURCE_PATH):
    """Read only the named source sheet. No workbook refresh, formulas or macros run."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        rels = {n.attrib['Id']: n.attrib['Target'] for n in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        workbook = ET.fromstring(z.read('xl/workbook.xml'))
        sheets = [n for n in workbook.findall('s:sheets/s:sheet', NS) if n.attrib['name'] == '统一达人库']
        if len(sheets) != 1:
            raise ValueError('源工作簿必须包含唯一的“统一达人库”工作表。')
        target = rels[sheets[0].attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
        target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        rows = []
        for row in ET.fromstring(z.read(target)).findall('s:sheetData/s:row', NS):
            values, kinds = {}, {}
            for cell in row.findall('s:c', NS):
                if cell.find('s:f', NS) is not None:
                    raise ValueError('源表包含公式，需先人工确认其观测值。')
                column = re.sub(r'\d', '', cell.attrib['r'])
                value = cell.find('s:v', NS)
                value = value.text if value is not None else ''
                kind = cell.attrib.get('t', 'n')
                if kind == 's':
                    value = shared[int(value)]
                elif kind == 'inlineStr':
                    inline = cell.find('s:is', NS)
                    value = ''.join(inline.itertext()) if inline is not None else ''
                values[column], kinds[column] = value or '', kind
            rows.append((int(row.attrib['r']), values, kinds))
    if not rows:
        raise ValueError('源表为空。')
    header = rows[0][1]
    if not set(FIELD_MAP).issubset(set(header.values())):
        raise ValueError('源表缺少必要字段。')
    records = []
    for number, values, kinds in rows[1:]:
        if not any(values.values()):
            continue
        record = {title: values.get(column, '') for column, title in header.items()}
        id_column = next(c for c, title in header.items() if title == '账号ID')
        record['_id_cell_type'], record['_row'] = kinds.get(id_column, 'n'), number
        records.append(record)
    return records


def normalize_source(records, source_path=SOURCE_PATH):
    """Preserve source IDs/values. Descriptions remain attributed third-party text."""
    source_hash = sha256(Path(source_path).read_bytes()).hexdigest()
    accounts, reviews = [], []
    reasons = {'identity': '账号身份及主页尚未人工核验。', 'content': '尚无已核实的近期内容证据。',
               'fit': '尚未完成产品适配评价。', 'subject_type': '账号主体类型待人工审核。',
               'model': '前置审核未完成，且尚未配置经审核的独立投放假设。'}
    for source in records:
        row = dict.fromkeys(ACCOUNT_FIELDS, '')
        row.update({target: source.get(original, '') for original, target in FIELD_MAP.items()})
        raw_id = row['platform_account_id']
        try:
            unsafe = source['_id_cell_type'] == 'n' and abs(Decimal(raw_id)) >= Decimal(10) ** 15
        except InvalidOperation:
            unsafe = True
        row.update(account_id_source_cell_type=source['_id_cell_type'],
            account_id_precision_status='precision_loss_risk' if unsafe else 'unverified',
            metric_basis='统计分母、样本量、窗口与更新时间待核实',
            source_date_basis='用户提供的导出日期，不等同于各指标测量日期',
            identity_data_type='third_party_reported', source_workbook=Path(source_path).name,
            source_sheet='统一达人库', source_row=str(source['_row']), source_workbook_sha256=source_hash,
            entity_link_status='pending', subject_type_hint='unknown')
        # This is a source-text hint, not approval or an independent identity finding.
        position = row['reported_position']
        if '品牌频道' in position:
            row['subject_type_hint'] = 'brand_channel_reported'
        elif '制造商' in position:
            row['subject_type_hint'] = 'manufacturer_reported'
        accounts.append(row)
        review = dict.fromkeys(REVIEW_FIELDS, '')
        review['creator_id'] = row['creator_id']
        for stage in STAGES:
            review[f'{stage}_status'], review[f'{stage}_reason'] = 'pending', reasons[stage]
        if row['subject_type_hint'] != 'unknown':
            review['subject_type_reason'] += '导出描述提示品牌频道或制造商，不默认视为独立创作者。'
        reviews.append(review)
    return {'accounts': pd.DataFrame(accounts, columns=ACCOUNT_FIELDS),
            'reviews': pd.DataFrame(reviews, columns=REVIEW_FIELDS),
            'evidence': pd.DataFrame(columns=EVIDENCE_FIELDS),
            'assumptions': pd.DataFrame(columns=ASSUMPTION_FIELDS)}


def _present(value):
    return pd.notna(value) and str(value).strip() != ''


def _numeric(data, fields):
    for field in fields:
        original = data[field]
        values = pd.to_numeric(original, errors='coerce')
        present = original.map(_present)
        if values[present].isna().any() or not values[present].map(lambda v: math.isfinite(v) and v >= 0).all():
            raise ValueError(f'数值字段无效：{field}')
        data[field] = pd.Series(values, index=data.index, dtype='Float64')


def _iso(value):
    if _present(value):
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value)):
                raise ValueError
            date.fromisoformat(str(value))
        except ValueError as exc:
            raise ValueError('日期必须为 YYYY-MM-DD。') from exc


def validate_registry(tables):
    """Validate copies; an empty evidence/assumptions table is intentional."""
    result = {key: value.copy(deep=True).replace('', pd.NA) for key, value in tables.items()}
    for key, (_, required) in FILES.items():
        if key not in result or not set(required).issubset(result[key].columns):
            raise ValueError(f'数据表缺少必要字段：{key}')
    accounts, reviews = result['accounts'], result['reviews']
    if accounts.empty or accounts.creator_id.isna().any() or accounts.creator_id.duplicated().any():
        raise ValueError('账号库不能为空，creator_id 必须非空且唯一。')
    for field in ('platform', 'handle', 'profile_url', 'platform_account_id', 'data_source', 'export_date',
                  'source_file', 'metric_basis', 'source_date_basis', 'source_workbook_sha256'):
        if not accounts[field].map(_present).all():
            raise ValueError(f'账号库缺少必要资料：{field}')
    if not accounts.platform.isin(PLATFORMS).all():
        raise ValueError('平台无效。')
    if not accounts.identity_data_type.eq('third_party_reported').all():
        raise ValueError('第三方导出不能标记为已核实观测。')
    if set(PARAMETERS).intersection(accounts.columns):
        raise ValueError('真实账号库不得混入投放假设。')
    if not accounts.platform_account_id.map(lambda v: isinstance(v, str)).all():
        raise ValueError('平台账号 ID 必须为文本，不得转换为数值。')
    if not accounts.account_id_precision_status.isin(['unverified', 'precision_loss_risk']).all():
        raise ValueError('来源账号 ID 的精度风险标记无效。')
    for _, row in accounts.iterrows():
        if row.account_id_source_cell_type == 'n':
            try:
                unsafe = abs(Decimal(row.platform_account_id)) >= Decimal(10) ** 15
            except InvalidOperation:
                unsafe = True
            if unsafe and row.account_id_precision_status != 'precision_loss_risk':
                raise ValueError('长数值账号 ID 必须保留精度丢失风险标记。')
        if urlparse(row.profile_url).scheme != 'https':
            raise ValueError('主页必须使用 HTTPS 链接。')
        _iso(row.export_date)
        if row.entity_link_status not in ('pending', 'verified'):
            raise ValueError('主体关联状态无效。')
        if _present(row.entity_id) or row.entity_link_status == 'verified':
            if row.entity_link_status != 'verified' or not all(_present(row[f]) for f in
                    ('entity_id', 'entity_link_evidence', 'entity_link_checked_by', 'entity_link_checked_at')):
                raise ValueError('主体关联必须有人工核实依据、审核人与日期。')
            _iso(row.entity_link_checked_at)
    _numeric(accounts, NUMERIC_ACCOUNT_FIELDS)
    if accounts.reported_followers.dropna().mod(1).ne(0).any():
        raise ValueError('粉丝数必须为整数。')
    for field in ('reported_mean_engagement_rate', 'reported_median_engagement_rate', 'us_audience_share'):
        if accounts[field].dropna().gt(1).any():
            raise ValueError(f'比例必须在 0 至 1 之间：{field}')
    if accounts.loc[accounts.us_audience_share.notna(), 'us_audience_evidence'].isna().any():
        raise ValueError('美国受众比例必须有独立证据，不能由创作者地区推断。')
    if reviews.creator_id.duplicated().any() or set(reviews.creator_id) != set(accounts.creator_id):
        raise ValueError('审核表必须按 creator_id 与账号库一对一对应。')
    for stage in STAGES:
        if not reviews[f'{stage}_status'].isin(['pending', 'approved', 'rejected']).all():
            raise ValueError(f'审核状态无效：{stage}')
        for _, row in reviews.iterrows():
            if not _present(row[f'{stage}_reason']):
                raise ValueError('每个审核阶段必须记录原因。')
            if row[f'{stage}_status'] != 'pending' and not all(_present(row[f'{stage}_{suffix}']) for suffix in ('checked_by', 'checked_at')):
                raise ValueError('已审核状态必须有审核人与日期。')
            _iso(row[f'{stage}_checked_at'])
    platforms = accounts.set_index('creator_id').platform.to_dict()
    for key in ('evidence', 'assumptions'):
        table = result[key]
        for _, row in table.iterrows():
            if not _present(row.creator_id) or row.creator_id not in platforms or not _present(row.platform) or row.platform != platforms[row.creator_id]:
                raise ValueError(f'{key} 引用了未知账号或不匹配的平台。')
    evidence = result['evidence']
    if evidence.evidence_id.isna().any() or evidence.evidence_id.duplicated().any():
        raise ValueError('evidence_id 必须非空且唯一。')
    _numeric(evidence, ('visible_views', 'visible_likes', 'visible_comments'))
    if not evidence.verification_status.isin(['pending', 'verified', 'rejected']).all():
        raise ValueError('内容证据核验状态无效。')
    for _, row in evidence.iterrows():
        for field in ('post_date', 'checked_at'):
            _iso(row[field])
        if row.verification_status == 'verified':
            required = ('post_url', 'post_date', 'content_format', 'content_topic', 'evidence_source', 'checked_at', 'product_relevance_reason')
            if not all(_present(row[f]) for f in required) or urlparse(row.post_url).scheme != 'https':
                raise ValueError('已核实内容必须有原帖、日期、格式、来源及适配依据。')
    assumptions = result['assumptions']
    if assumptions.creator_id.duplicated().any():
        raise ValueError('每个账号只能有一条当前基础假设。')
    if not assumptions.model_data_type.eq('simulated').all():
        raise ValueError('投放参数必须明确标记为 simulated。')
    if not assumptions.assumption_status.isin(['pending', 'approved', 'rejected']).all():
        raise ValueError('投放参数审核状态无效。')
    _numeric(assumptions, PARAMETERS)
    for field in ('assumed_engagement_rate', 'assumed_ctr', 'assumed_cvr'):
        if assumptions[field].dropna().gt(1).any():
            raise ValueError('模型率必须在 0 至 1 之间。')
    for field in ('assumed_audience_match_score', 'assumed_content_quality_score'):
        if assumptions[field].dropna().gt(100).any():
            raise ValueError('假设分数必须在 0 至 100 之间。')
    for _, row in assumptions.iterrows():
        _iso(row.checked_at)
        if _present(row.estimated_fee_usd):
            fee = Decimal(str(row.estimated_fee_usd))
            if fee <= 0 or fee != fee.quantize(Decimal('0.01')):
                raise ValueError('模拟报价必须为正数，且最多两位小数。')
        if _present(row.estimated_reach) and row.estimated_reach % 1 != 0:
            raise ValueError('模拟单条触达必须为整数，不得把历史中位播放量直接转入。')
        if row.assumption_status == 'approved':
            required = (*PARAMETERS, *(f'{p}_source' for p in PARAMETERS), 'content_format',
                        'assumption_version', 'planning_basis', 'checked_by', 'checked_at')
            if not all(_present(row[f]) for f in required) or row.engagement_rate_basis != 'reach':
                raise ValueError('已批准假设必须有完整参数、逐项来源及触达分母说明。')
    return result


def load_registry(directory=REGISTRY_DIR):
    tables = {}
    for key, (filename, _) in FILES.items():
        try:
            tables[key] = pd.read_csv(Path(directory) / filename, dtype='string', keep_default_na=False, encoding='utf-8-sig')
        except (OSError, ValueError) as exc:
            raise ValueError(f'无法读取账号研究数据表：{filename}') from exc
    return validate_registry(tables)


def audit_registry(tables):
    """A prerequisite audit only. Does not adapt any row into the old optimizer."""
    tables = validate_registry(tables)
    accounts = tables['accounts']; reviews = tables['reviews'].set_index('creator_id')
    evidence = tables['evidence']; assumptions = tables['assumptions'].set_index('creator_id')
    rows = []
    for _, account in accounts.iterrows():
        review = reviews.loc[account.creator_id]; reasons = []
        for stage in STAGES:
            if review[f'{stage}_status'] != 'approved':
                reasons.append(review[f'{stage}_reason'])
        content = evidence.loc[(evidence.creator_id == account.creator_id) & (evidence.verification_status == 'verified')]
        if content.empty:
            reasons.append('没有已核实的内容证据。')
        if not _present(account.confirmed_subject_type):
            reasons.append('主体类型尚未确认。')
        elif account.confirmed_subject_type not in ('creator', 'pet_account', 'multi_pet_household'):
            reasons.append('品牌、制造商或其他非典型主体须另行评估，不进入当前正式池。')
        if account.creator_id not in assumptions.index or assumptions.loc[account.creator_id, 'assumption_status'] != 'approved':
            reasons.append('缺少已批准的独立模拟投放假设。')
        completed = [stage for stage in STAGES if review[f'{stage}_status'] == 'approved']
        rows.append(dict(creator_id=account.creator_id, platform=account.platform,
            identity_verified='identity' in completed, content_reviewed='content' in completed,
            fit_reviewed='fit' in completed, subject_type_reviewed='subject_type' in completed,
            model_eligible=not reasons,
            review_progress=('具备投放模型资格' if not reasons else '待核验' if 'identity' not in completed
                else '已完成适配评价' if 'fit' in completed else '已完成内容审核' if 'content' in completed else '已核验身份'),
            pending_reasons='；'.join(str(r) for r in reasons)))
    return pd.DataFrame(rows)


def import_workbook(path=SOURCE_PATH, directory=REGISTRY_DIR):
    """Explicit, non-overwriting import. Never called by the Streamlit app."""
    from deployment_policy import require_server_write
    require_server_write('导入工作簿并写入CSV')
    tables = normalize_source(read_source_workbook(path), path)
    accounts = tables['accounts']
    if set(accounts.creator_id) != {f'KOL-{i:03}' for i in range(1, 53)} or accounts.platform.value_counts().to_dict() != {'Instagram': 20, 'TikTok': 20, 'YouTube': 12}:
        raise ValueError('本批导入必须保留 KOL-001 至 KOL-052 及 20/20/12 平台分布。')
    validate_registry(tables)
    directory = Path(directory)
    if any((directory / filename).exists() for filename, _ in FILES.values()):
        raise FileExistsError('目标数据已存在；禁止自动覆盖，需人工确认新版本。')
    directory.mkdir(parents=True, exist_ok=True)
    for key, (filename, fields) in FILES.items():
        with (directory / filename).open('x', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(tables[key].to_dict('records'))
    return load_registry(directory)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='一次性导入三平台研究底表，不覆盖已有数据。')
    parser.add_argument('--source', type=Path, default=SOURCE_PATH)
    parser.add_argument('--output-dir', type=Path, default=REGISTRY_DIR)
    args = parser.parse_args()
    imported = import_workbook(args.source, args.output_dir)
    print('Imported:', len(imported['accounts']), 'platform accounts; eligible:', int(audit_registry(imported).model_eligible.sum()))
