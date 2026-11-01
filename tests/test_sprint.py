"""Registry truth boundaries, human gate, and real optimizer scenario regression."""
from pathlib import Path
from tempfile import TemporaryDirectory
import copy
import unittest
import os
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from creator_registry import load_registry, audit_registry, STAGES, PARAMETERS
from sprint_research import (screen_accounts, deep_research, score_registry,
                             save_human_review, load_human_reviews, apply_event)
from sprint_decision import (adapt_model, sandbox_assumptions, run_plan, scenario_suite,
                             selection_explanations, safe_csv)

ROOT = Path(__file__).resolve().parents[1]


class SprintDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = load_registry()
        cls.screen = screen_accounts(cls.tables['accounts'])
        cls.model = adapt_model(cls.tables, cls.screen, sandbox=True)

    def test_all_accounts_and_balanced_focus_preserved(self):
        self.assertEqual(len(self.screen), 52)
        self.assertEqual(self.screen.groupby('platform').focus_candidate.sum().to_dict(),
                         {'Instagram': 4, 'TikTok': 4, 'YouTube': 4})
        focus = self.screen.query('focus_candidate')
        self.assertFalse(focus.subject_risk.eq('品牌/制造商线索').any())
        deep = deep_research(self.screen)
        self.assertEqual(len(deep), 12)
        self.assertEqual(deep.posts_collected.sum(), 0)
        self.assertTrue(deep.analysis_scope.str.contains('未观看视频').all())
        self.assertTrue(self.screen.source_reference.str.contains('HiCreator').all())

    def test_handle_alone_never_classifies_unknown(self):
        account = self.tables['accounts'].iloc[[0]].copy()
        account['reported_description'] = pd.NA
        account['reported_position'] = pd.NA
        account['handle'] = 'PETKIT_智能喂食器_多猫_测评'
        result = screen_accounts(account).iloc[0]
        self.assertEqual(result.categories, 'Unknown')
        self.assertEqual(result.priority, 0)

    def test_screening_never_modifies_human_tables_or_approves(self):
        before = copy.deepcopy(self.tables)
        screen_accounts(self.tables['accounts'])
        adapt_model(self.tables, self.screen, True)
        score_registry(self.tables, self.screen, model=self.model)
        for key in before:
            pd.testing.assert_frame_equal(before[key], self.tables[key])
        self.assertEqual(int(audit_registry(self.tables).model_eligible.sum()), 0)
        self.assertTrue(adapt_model(self.tables, self.screen).empty)

    def test_unknown_scores_stay_missing_and_complete_score_not_invented(self):
        scores = score_registry(self.tables, self.screen, model=self.model)
        self.assertTrue(scores['产品内容适配度'].isna().all())
        self.assertTrue(scores.total_score.isna().all())
        self.assertTrue(scores.evidence_coverage.eq(0).all())
        self.assertTrue(scores.loc[~scores.creator_id.isin(self.model.creator_id), '模拟预算效率'].isna().all())
        accounts = self.tables['accounts'].copy()
        accounts.loc[0, ['reported_median_views', 'reported_mean_engagement_rate']] = pd.NA
        tables = {**self.tables, 'accounts': accounts}
        s = score_registry(tables, screen_accounts(accounts), model=self.model).iloc[0]
        self.assertTrue(pd.isna(s['内容表现']))
        self.assertTrue(pd.isna(s['互动表现']))

    def test_simulation_templates_independent_of_historical_metrics(self):
        changed = self.tables['accounts'].copy()
        changed['reported_followers'] = 1
        changed['reported_median_views'] = 9999999
        changed['reported_mean_engagement_rate'] = .999
        pd.testing.assert_frame_equal(sandbox_assumptions(changed, self.screen),
                                      sandbox_assumptions(self.tables['accounts'], self.screen))

    def test_budget_objective_and_assumptions_are_actual_optimizations(self):
        suite = scenario_suite(self.model)
        self.assertEqual(len(suite), 12)
        budget = suite.query("family == '预算变化'").set_index('scenario')
        self.assertNotEqual(budget.loc['$3,000', 'selected_ids'], budget.loc['$5,000', 'selected_ids'])
        self.assertTrue((suite.spent_usd <= suite.budget_usd).all())
        objectives = suite.query("family == '目标变化'").set_index('scenario')
        self.assertNotEqual(objectives.loc['Engagement', 'selected_ids'], objectives.loc['Brand Awareness', 'selected_ids'])
        self.assertEqual(objectives.loc['Conversion', 'selected_ids'], objectives.loc['Brand Awareness', 'selected_ids'])
        assumptions = suite.query("family == '效果假设' and calculation == '固定基准组合'").set_index('scenario')
        self.assertAlmostEqual(assumptions.loc['Conservative', 'conversions'] / assumptions.loc['Base', 'conversions'], .25)
        self.assertEqual(len(set(assumptions.selected_ids)), 1)

    def test_whatif_fee_override_isolated_and_exits_are_explained(self):
        original = self.model.copy(deep=True)
        baseline = run_plan(self.model)
        creator_id = baseline.selected.iloc[0].creator_id
        changed = run_plan(self.model, fee_overrides={creator_id: 11000})
        self.assertNotIn(creator_id, set(changed.selected.creator_id))
        reasons = selection_explanations(self.tables, self.screen, changed, 'Brand Awareness').set_index('creator_id')
        self.assertEqual(reasons.loc[creator_id, 'status'], '预算约束')
        self.assertIn('资格不足', reasons.loc[creator_id, 'formal_eligibility'])
        pd.testing.assert_frame_equal(original, self.model)

    def test_invalid_whatif_inputs_rejected(self):
        for override in ({'KOL-999': 500}, {'KOL-003': -1}, {'KOL-003': 1.111}):
            with self.assertRaises(ValueError):
                run_plan(self.model, fee_overrides=override)
        for rate in (-1, 1.1, float('nan')):
            with self.assertRaises(ValueError):
                run_plan(self.model, ctr=rate)

    def test_empty_formal_suite_is_honest_and_export_is_inert(self):
        suite = scenario_suite(adapt_model(self.tables, self.screen))
        self.assertTrue(suite.creator_count.eq(0).all())
        self.assertTrue(suite.cpa_usd.isna().all())
        csv = safe_csv(pd.DataFrame({'text': ['=HYPERLINK("x")', '+cmd', 'Unknown'], 'metric': [None, 0, 2]})).decode('utf-8-sig')
        self.assertIn("'=HYPERLINK", csv)
        self.assertIn("'+cmd", csv)

    def human_update(self):
        creator_id = 'KOL-003'
        review = {'creator_id': creator_id}
        for stage in STAGES:
            review.update({f'{stage}_status': 'approved', f'{stage}_reason': '测试人工依据',
                           f'{stage}_checked_by': 'test reviewer', f'{stage}_checked_at': '2026-10-30'})
        assumption = dict(creator_id=creator_id, platform='Instagram', content_format='短视频', model_data_type='simulated',
            assumption_status='approved', assumption_version='human-test', planning_basis='测试独立模拟', engagement_rate_basis='reach',
            checked_by='test reviewer', checked_at='2026-10-30',
            **sandbox_assumptions(self.tables['accounts'], self.screen).set_index('creator_id').loc[creator_id, list(PARAMETERS)].to_dict())
        assumption.update({p + '_source': 'test simulated source' for p in PARAMETERS})
        return {'reviews': [review], 'accounts': [{'creator_id': creator_id, 'confirmed_subject_type': 'creator'}], 'assumptions': [assumption]}

    def test_human_approval_alone_cannot_bypass_content_gate(self):
        event = dict(reviewer='human', reason='test', updates=self.human_update())
        tables = apply_event(self.tables, event)
        self.assertFalse(audit_registry(tables).model_eligible.any())
        self.assertTrue(adapt_model(tables, self.screen).empty)

    def test_verified_post_plus_complete_human_workflow_enables_only_one(self):
        updates = self.human_update()
        # Test fixture only: an illustrative URL is never written to production data.
        updates['evidence'] = [dict(evidence_id='TEST-ONLY', creator_id='KOL-003', platform='Instagram',
            post_url='https://www.instagram.com/p/TEST_ONLY/', post_date='2026-10-30', content_format='短视频',
            content_topic='多猫智能喂食器测评', evidence_source='test fixture only', checked_at='2026-10-30',
            verification_status='verified', product_relevance_reason='test relevance')]
        with TemporaryDirectory() as temp, patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'local_dev'}):
            saved = save_human_review(self.tables, updates, 'human', 'test', directory=temp)
            loaded = load_human_reviews(self.tables, directory=temp)
            self.assertEqual(int(audit_registry(loaded).model_eligible.sum()), 1)
            self.assertEqual(adapt_model(loaded, self.screen).creator_id.tolist(), ['KOL-003'])
            scores = score_registry(loaded, self.screen, model=adapt_model(loaded, self.screen)).set_index('creator_id')
            self.assertEqual(scores.loc['KOL-003', '产品内容适配度'], 100)
            self.assertEqual(scores.loc['KOL-003', 'score_completeness'], 1)
            self.assertFalse(pd.isna(scores.loc['KOL-003', 'total_score']))
            self.assertEqual(len(list(Path(temp).glob('*.json'))), 1)
            pd.testing.assert_frame_equal(saved['reviews'], loaded['reviews'])

    def test_invalid_review_does_not_write_log_or_mutate_source(self):
        with TemporaryDirectory() as temp, patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'local_dev'}):
            with self.assertRaises(ValueError):
                save_human_review(self.tables, self.human_update(), '', 'reason', directory=temp)
            with self.assertRaises(ValueError):
                save_human_review(self.tables, {'accounts': [{'creator_id': 'KOL-003', 'reported_followers': 999}]}, 'human', 'reason', directory=temp)
            self.assertEqual(list(Path(temp).iterdir()), [])


class SprintAppTests(unittest.TestCase):
    def open_app(self):
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=60).run()
        return app.radio(key='presentation_mode').set_value('Research Workspace').run()

    def test_default_real_registry_and_no_auto_approval(self):
        app = self.open_app()
        self.assertFalse(app.exception)
        metrics = {item.label: item.value for item in app.metric}
        self.assertEqual(metrics['真实平台账号记录'], '52')
        self.assertEqual(metrics['重点研究候选'], '12')
        self.assertEqual(metrics['正式推荐资格'], '0')
        self.assertEqual(len(app.tabs), 5)
        app.radio(key='sprint_mode').set_value('正式推荐（仅已批准）').run()
        self.assertFalse(app.exception)
        self.assertEqual(next(m.value for m in app.metric if m.label == '入选人数'), '0')
        self.assertFalse(any(b.label == '下载当前模拟组合 CSV' for b in app.get('download_button')))

    def test_platform_budget_objective_assumptions_and_whatif(self):
        app = self.open_app()
        app.number_input(key='sprint_budget').set_value(3000).run()
        self.assertFalse(app.exception)
        self.assertEqual(next(m.value for m in app.metric if m.label == '已使用预算（美元）'), '2,900.00')
        app.selectbox(key='sprint_objective').set_value('Conversion')
        app.selectbox(key='sprint_assumption').set_value('Conservative').run()
        self.assertFalse(app.exception)
        app.number_input(key='whatif_fee_KOL-003').set_value(11000).run()
        self.assertFalse(app.exception)
        app.multiselect(key='sprint_platforms').set_value(['YouTube']).run()
        self.assertFalse(app.exception)
        screen = app.tabs[1].dataframe[0].value
        self.assertEqual(len(screen), 12)
        self.assertEqual(set(screen.platform), {'YouTube'})
        app.multiselect(key='sprint_platforms').set_value([]).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('请选择至少一个平台' in item.value for item in app.info))


if __name__ == '__main__':
    unittest.main()
