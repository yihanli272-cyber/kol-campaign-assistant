from io import BytesIO
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from kol_data import load_kol_data, score_kols, validate_kol_data
from portfolio import export_portfolio_csv, optimize_portfolio
from research_data import (PARAMETER_MAP, load_real_kols, load_campaign_assumptions,
                           prepare_research_model, research_fingerprint)


class ResearchDataTests(unittest.TestCase):
    def setUp(self):
        self.research = load_real_kols()
        self.assumptions = load_campaign_assumptions()

    def test_both_datasets_load_without_replacing_mock(self):
        self.assertEqual(len(load_kol_data()), 30)
        self.assertEqual(len(self.research), 30)
        self.assertEqual(len(self.assumptions), 30)
        self.assertEqual(self.research.platform.value_counts().to_dict(), {'Instagram': 28, 'TikTok': 2})

    def test_approved_report_missing_values_and_statuses_preserved(self):
        self.assertEqual(self.research.followers.notna().sum(), 1)
        rigby = self.research.set_index('creator_id').loc['REAL003']
        self.assertEqual(rigby.followers, 2344134)
        self.assertEqual(rigby.source_data_date, '2026-10-17')
        self.assertTrue(self.research.observed_engagement_rate.isna().all())
        self.assertTrue(self.research.recent_post_url.isna().all())
        self.assertEqual(self.research.visible_comments.dropna().tolist(), [222, 122])
        self.assertTrue(self.research.verification_status.eq('partially_verified').all())
        self.assertEqual(self.research.verification_tier.eq('B').sum(), 2)

    def test_only_explicit_complete_templates_are_eligible(self):
        audit, model = prepare_research_model(self.research, self.assumptions)
        self.assertEqual(set(model.creator_id), {'REAL001', 'REAL002', 'REAL011', 'REAL013', 'REAL014'})
        self.assertEqual(audit.model_eligible.sum(), 5)
        self.assertTrue(audit.loc[~audit.model_eligible, 'model_eligibility_reason'].str.contains('Missing').all())
        self.assertTrue(model.followers.isna().all())
        self.assertTrue(model.model_data_type.eq('simulated').all())
        self.assertTrue(model.identity_data_type.eq('public_profile').all())
        self.assertFalse(set(PARAMETER_MAP).intersection(self.research.columns))

    def test_id_join_works_after_independent_reordering(self):
        assumptions = self.assumptions.copy()
        assumptions.loc[assumptions.creator_id.eq('REAL001'), 'estimated_fee_usd'] = 700
        _, model = prepare_research_model(self.research.sample(frac=1, random_state=3), assumptions.sample(frac=1, random_state=9))
        self.assertEqual(model.set_index('creator_id').loc['REAL001', 'estimated_fee_usd'], 700)
        self.assertEqual(model.set_index('creator_id').loc['REAL002', 'estimated_fee_usd'], 500)

    def test_missing_assumption_row_is_not_imputed(self):
        audit, model = prepare_research_model(self.research, self.assumptions.loc[~self.assumptions.creator_id.eq('REAL001')])
        self.assertNotIn('REAL001', set(model.creator_id))
        row = audit.set_index('creator_id').loc['REAL001']
        self.assertTrue(pd.isna(row.estimated_fee_usd))
        self.assertIn('no assumption row', row.model_eligibility_reason)

    def test_invalid_missing_and_unsourced_parameters_are_excluded(self):
        for field, value in [('estimated_fee_usd', -1), ('estimated_reach', float('nan')), ('assumed_ctr', 2), ('assumed_engagement_rate_source', '')]:
            assumptions = self.assumptions.copy()
            assumptions.loc[assumptions.creator_id.eq('REAL001'), field] = value
            with self.subTest(field=field):
                audit, model = prepare_research_model(self.research, assumptions)
                self.assertNotIn('REAL001', set(model.creator_id))
                self.assertFalse(audit.set_index('creator_id').loc['REAL001', 'model_eligible'])

    def test_disabled_even_with_complete_numbers_stays_excluded(self):
        assumptions = self.assumptions.copy()
        assumptions.loc[assumptions.creator_id.eq('REAL001'), 'model_enabled'] = False
        _, model = prepare_research_model(self.research, assumptions)
        self.assertNotIn('REAL001', set(model.creator_id))

    def test_all_disabled_and_valid_decimal_fee(self):
        assumptions = self.assumptions.assign(model_enabled=False)
        audit, model = prepare_research_model(self.research, assumptions)
        self.assertFalse(audit.model_eligible.any())
        self.assertTrue(optimize_portfolio(model, 5000).selected.empty)
        assumptions = self.assumptions.copy()
        assumptions.loc[assumptions.creator_id.eq('REAL001'), 'estimated_fee_usd'] = 500.29
        _, model = prepare_research_model(self.research, assumptions)
        self.assertIn('REAL001', set(model.creator_id))

    def test_observed_metrics_never_become_model_parameters(self):
        changed = self.research.copy()
        changed['observed_engagement_rate'] = .9
        changed['visible_views'] = 9_000_000
        changed['us_audience_share'] = .99
        _, model = prepare_research_model(changed, self.assumptions)
        self.assertTrue(model.engagement_rate.eq(.05).all())
        self.assertTrue(model.estimated_reach.eq(20000).all())
        self.assertTrue(model.audience_match_score.eq(70).all())

    def test_unknown_and_duplicate_ids_raise_clear_errors(self):
        unknown = self.assumptions.copy()
        unknown.loc[0, 'creator_id'] = 'UNKNOWN'
        with self.assertRaisesRegex(ValueError, 'unknown creator_id'):
            prepare_research_model(self.research, unknown)
        with self.assertRaisesRegex(ValueError, 'unique creator_id'):
            prepare_research_model(self.research, pd.concat([self.assumptions, self.assumptions.iloc[[0]]]))

    def test_hybrid_model_has_explicit_provenance_and_missing_followers(self):
        _, model = prepare_research_model(self.research, self.assumptions)
        self.assertTrue(validate_kol_data(model).followers.isna().all())
        invalid = model.copy()
        invalid['model_data_type'] = 'observed'
        with self.assertRaisesRegex(ValueError, 'model_data_type=simulated'):
            validate_kol_data(invalid)
        reasons = score_kols(model).recommendation_reason
        self.assertTrue(reasons.str.contains('Public research:').all())
        self.assertTrue(reasons.str.contains('Research interpretation:').all())
        self.assertTrue(reasons.str.contains('SIMULATED model:').all())

    def test_existing_optimizer_and_forecast_work_for_model_subset(self):
        _, model = prepare_research_model(self.research, self.assumptions)
        result = optimize_portfolio(model, 1000)
        self.assertEqual(result.metrics['spent_usd'], 1000)
        self.assertEqual(result.metrics['creator_count'], 2)
        self.assertEqual(result.metrics['target_reach'], 28000)
        self.assertAlmostEqual(result.metrics['conversions'], 11.2)
        self.assertTrue(result.selected.creator_id.is_unique)
        zero = optimize_portfolio(model, 0)
        self.assertTrue(zero.selected.empty)

    def test_research_export_keeps_both_provenances_and_blanks(self):
        _, model = prepare_research_model(self.research, self.assumptions)
        result = optimize_portfolio(model, 1000)
        csv = pd.read_csv(BytesIO(export_portfolio_csv(result, {'dataset': 'Real Creator Research Dataset'})))
        self.assertTrue(csv.followers.isna().all())
        self.assertTrue(csv.observed_engagement_rate.isna().all())
        self.assertTrue(csv.engagement_rate.eq(.05).all())
        self.assertTrue(csv.data_type.eq('hybrid_public_identity_simulated_model').all())
        self.assertTrue(csv.verification_status.eq('partially_verified').all())
        self.assertTrue(csv.estimated_fee_usd_source.str.contains('not creator quote').all())
        self.assertFalse(csv.simulation_notice.str.contains('SIMULATED creators').any())

    def test_fingerprint_covers_all_research_and_assumption_rows(self):
        original = research_fingerprint(self.research, self.assumptions)
        changed = self.research.copy()
        changed.loc[29, 'notes'] = 'new research information'
        self.assertNotEqual(original, research_fingerprint(changed, self.assumptions))
        changed = self.assumptions.copy()
        changed.loc[29, 'exclusion_reason'] = 'new review finding'
        self.assertNotEqual(original, research_fingerprint(self.research, changed))

    def test_reader_rejects_false_verification_and_parameter_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'research.csv'
            changed = self.research.copy()
            changed.loc[0, 'verification_status'] = 'fully_verified'
            changed.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'fully verified'):
                load_real_kols(path)
            changed = self.research.assign(estimated_fee_usd=500)
            changed.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'must not be stored'):
                load_real_kols(path)

    def test_reader_rejects_observed_assumption_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'assumptions.csv'
            self.assumptions.assign(model_data_type='observed').to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'labeled simulated'):
                load_campaign_assumptions(path)


if __name__ == '__main__':
    unittest.main()
