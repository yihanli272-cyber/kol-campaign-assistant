from pathlib import Path
import re
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from kol_data import load_kol_data, score_kols
from portfolio import optimize_portfolio
from research_data import load_campaign_assumptions, load_real_kols, prepare_research_model
from ui_zh import column_label, display_frame, text_zh


ROOT = Path(__file__).resolve().parents[1]


class ChineseDisplayTests(unittest.TestCase):
    def test_research_and_assumption_display_preserves_raw_data(self):
        research = load_real_kols()
        assumptions = load_campaign_assumptions()
        before_research = research.copy(deep=True)
        before_assumptions = assumptions.copy(deep=True)
        translated = display_frame(research)
        parameter_view = display_frame(assumptions)
        pd.testing.assert_frame_equal(research, before_research)
        pd.testing.assert_frame_equal(assumptions, before_assumptions)
        pd.testing.assert_series_equal(translated.followers, research.followers)
        pd.testing.assert_series_equal(translated.profile_url, research.profile_url)
        pd.testing.assert_series_equal(translated.creator_name, research.creator_name)
        self.assertTrue(translated.verification_status.eq('部分核实').all())
        for field in ('fit_rationale', 'source_date_basis', 'follower_count_notes', 'engagement_rate_basis',
                      'us_audience_evidence', 'petkit_collaboration_evidence', 'competitor_collaboration_evidence',
                      'manual_review_fields', 'notes', 'creator_category'):
            for value in translated[field].dropna():
                self.assertRegex(value, r'[\u4e00-\u9fff]', msg=f'Untranslated research field: {field}')
        for field in assumptions.columns:
            if field.endswith('_source') or field in ('planning_basis', 'exclusion_reason'):
                for value in parameter_view[field].dropna():
                    self.assertRegex(value, r'[\u4e00-\u9fff]', msg=f'Untranslated assumption field: {field}')
            self.assertRegex(column_label(field), r'[\u4e00-\u9fff]')

    def test_localized_reasons_leave_scores_and_budget_results_unchanged(self):
        audit, model = prepare_research_model(load_real_kols(), load_campaign_assumptions())
        self.assertTrue(display_frame(audit).model_eligibility_reason.str.contains('模型|参数|建模').all())
        scored = score_kols(model)
        before = scored.copy(deep=True)
        translated = display_frame(scored)
        pd.testing.assert_frame_equal(before, scored)
        pd.testing.assert_series_equal(translated.total_score, scored.total_score)
        self.assertTrue(translated.recommendation_reason.str.contains('公开研究：').all())
        self.assertTrue(translated.recommendation_reason.str.contains('研究判断：').all())
        self.assertTrue(translated.recommendation_reason.str.contains('模拟模型：').all())
        result = optimize_portfolio(model, 1000)
        self.assertTrue(display_frame(result.selected).selection_reason.str.startswith('组合选择（模拟）').all())
        self.assertEqual(result.metrics['spent_usd'], 1000)
        self.assertAlmostEqual(result.metrics['conversions'], 11.2)
        self.assertTrue(display_frame(score_kols(load_kol_data())).recommendation_reason.str.startswith('模拟受众匹配').all())

    def test_error_messages_are_chinese_and_keep_field_details(self):
        for source in (
            'Missing required fields: followers',
            'followers must contain finite numbers between 1 and 10000000.',
            'Budget must be a finite non-negative USD amount with at most two decimal places.',
            'Excluded 2 invalid or duplicate creator records.',
            'No feasible positive-outcome portfolio: check filters, budget and per-creator execution costs.',
            'Data or model assumptions changed. Save a new baseline before comparing.',
        ):
            self.assertRegex(text_zh(source), r'[\u4e00-\u9fff]')
        self.assertIn('followers', text_zh('Missing required fields: followers'))
        with patch('kol_data.load_kol_data', side_effect=ValueError('Missing required fields: followers')):
            app = AppTest.from_file(str(ROOT / 'legacy_app.py'), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.error[0].value, '缺少必要字段：followers')

    def test_page_labels_and_dataset_switch_use_chinese_display(self):
        app = AppTest.from_file(str(ROOT / 'legacy_app.py'), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.title[0].value, 'AI KOL Campaign Decision Assistant')
        self.assertTrue(any(item.value == '海外 KOL 营销决策工作台' for item in app.caption))
        self.assertEqual(app.radio[0].options, ['模拟演示数据集', '真实创作者研究数据集'])
        self.assertEqual(app.selectbox[0].options, ['品牌认知', '互动提升', '转化提升'])
        self.assertEqual(app.button(key='save_baseline').label, '保存当前方案为基准方案')
        self.assertTrue(any('每千次调整触达成本' in metric.label for metric in app.metric))
        app.radio(key='dataset').set_value('Real Creator Research Dataset').run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('真实身份＋模拟规划' in item.value for item in app.warning))
        self.assertTrue(any(metric.label == '模型参数完整的候选' and metric.value == '5' for metric in app.metric))
        for dataframe in app.dataframe:
            if 'fit_rationale' in dataframe.value:
                self.assertTrue(dataframe.value.fit_rationale.str.contains(r'[\u4e00-\u9fff]', regex=True).all())
        app.multiselect[0].set_value([]).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('没有创作者满足' in item.value for item in app.info))


if __name__ == '__main__':
    unittest.main()
