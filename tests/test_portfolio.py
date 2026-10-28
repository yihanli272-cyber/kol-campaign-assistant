from io import BytesIO
from itertools import combinations
import unittest

import pandas as pd

from kol_data import load_kol_data
from portfolio import (optimize_portfolio, make_snapshot, compare_scenarios,
                       export_portfolio_csv, model_fingerprint, cents)


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.data = load_kol_data()

    def test_budget_count_unique_and_extra_costs(self):
        for budget in (0, 100, 500, 3000, 5000, 10000):
            with self.subTest(budget=budget):
                result = optimize_portfolio(self.data, budget, sample_usd=80, shipping_usd=20)
                self.assertLessEqual(result.metrics['spent_usd'], budget)
                self.assertLessEqual(len(result.selected), 6)
                if not result.selected.empty:
                    self.assertTrue(result.selected.creator_id.is_unique)
                    self.assertAlmostEqual(result.metrics['spent_usd'], result.selected.estimated_fee_usd.sum() + 100 * len(result.selected))

    def test_exact_optimum_matches_exhaustive_search(self):
        result = optimize_portfolio(self.data.iloc[:8], 2200, max_creators=3)
        rows = result.candidates.to_dict('records')
        feasible = [(sum(r['target_reach'] for r in group), sum(r['execution_cost_usd'] for r in group), tuple(sorted(r['creator_id'] for r in group)))
                    for count in range(4) for group in combinations(rows, count)
                    if sum(r['execution_cost_usd'] for r in group) <= 2200]
        best = min(feasible, key=lambda item: (-item[0], item[1], item[2]))
        self.assertAlmostEqual(result.metrics['target_reach'], best[0])
        self.assertEqual(tuple(sorted(result.selected.creator_id)), best[2])

    def test_budget_change_recalculates(self):
        low = optimize_portfolio(self.data, 500)
        high = optimize_portfolio(self.data, 5000)
        self.assertNotEqual(low.selected.creator_id.tolist(), high.selected.creator_id.tolist())
        self.assertGreater(high.metrics['target_reach'], low.metrics['target_reach'])

    def test_objective_changes_scores_and_portfolio(self):
        awareness = optimize_portfolio(self.data, 5000)
        conversion = optimize_portfolio(self.data, 5000, 'Conversion')
        self.assertFalse(awareness.candidates.total_score.equals(conversion.candidates.total_score))
        self.assertNotEqual(set(awareness.selected.creator_id), set(conversion.selected.creator_id))

    def test_empty_insufficient_zero_outcome(self):
        for data, budget in ((self.data.iloc[:0], 5000), (self.data, 1), (self.data.assign(estimated_reach=0), 5000)):
            result = optimize_portfolio(data, budget)
            self.assertTrue(result.selected.empty)
            self.assertEqual(result.metrics['spent_usd'], 0)
            self.assertIsNone(result.metrics['cpa_usd'])
            self.assertTrue(result.messages)

    def test_invalid_missing_fees_and_duplicate_ids_excluded(self):
        data = self.data.iloc[:5].copy()
        data.loc[data.index[0], 'estimated_fee_usd'] = float('nan')
        data.loc[data.index[1], 'estimated_fee_usd'] = -1
        data = pd.concat([data, data.iloc[[2]]], ignore_index=True)
        result = optimize_portfolio(data, 5000)
        self.assertTrue(set(result.selected.creator_id).issubset(set(self.data.iloc[3:5].creator_id)))
        self.assertIn('Excluded 4', result.messages[0])
        missing = optimize_portfolio(self.data.drop(columns='assumed_ctr'), 5000)
        self.assertTrue(missing.selected.empty)
        self.assertIn('Missing required fields', missing.messages[0])

    def test_forecast_formulas(self):
        data = self.data.iloc[[0]].assign(estimated_reach=10000, audience_match_score=80,
                                        engagement_rate=0.05, assumed_ctr=0.02,
                                        assumed_click_to_purchase_cvr=0.025, estimated_fee_usd=100)
        result = optimize_portfolio(data, 200, sample_usd=20, shipping_usd=10)
        expected = dict(raw_reach=10000, target_reach=8000, engagements=400, clicks=160,
                        conversions=4, spent_usd=130, remaining_usd=70,
                        cpm_usd=16.25, cpe_usd=0.325, cpc_usd=0.8125, cpa_usd=32.5)
        for key, value in expected.items():
            self.assertAlmostEqual(result.metrics[key], value, msg=key)

    def test_zero_rates_no_division_error(self):
        data = self.data.iloc[[0]].assign(engagement_rate=0, assumed_ctr=0)
        result = optimize_portfolio(data, 5000)
        self.assertIsNone(result.metrics['cpe_usd'])
        self.assertIsNone(result.metrics['cpc_usd'])
        self.assertIsNone(result.metrics['cpa_usd'])

    def test_snapshot_comparison_and_same_budget(self):
        fingerprint = model_fingerprint(self.data)
        low = make_snapshot(optimize_portfolio(self.data, 500), {'budget': 500}, fingerprint)
        high = make_snapshot(optimize_portfolio(self.data, 5000), {'budget': 5000}, fingerprint)
        compared = compare_scenarios(low, high).set_index('metric')
        self.assertEqual(compared.loc['budget_usd', 'absolute_change'], 4500)
        self.assertEqual(compare_scenarios(low, low).absolute_change.fillna(0).sum(), 0)
        high['fingerprint'] = 'new-data'
        with self.assertRaisesRegex(ValueError, 'Save a new baseline'):
            compare_scenarios(low, high)

    def test_empty_scenario_comparison(self):
        empty = make_snapshot(optimize_portfolio(self.data, 0), {}, 'same')
        full = make_snapshot(optimize_portfolio(self.data, 5000), {}, 'same')
        compared = compare_scenarios(empty, full).set_index('metric')
        self.assertTrue(pd.isna(compared.loc['target_reach', 'percent_change']))
        self.assertTrue(pd.isna(compared.loc['cpa_usd', 'absolute_change']))

    def test_csv_matches_current_result_and_is_excel_compatible(self):
        result = optimize_portfolio(self.data, 5000)
        content = export_portfolio_csv(result, {'brand': '测试品牌', 'budget_usd': 5000})
        self.assertTrue(content.startswith(b'\xef\xbb\xbf'))
        csv = pd.read_csv(BytesIO(content))
        self.assertEqual(csv.creator_id.tolist(), result.selected.creator_id.tolist())
        self.assertTrue(csv.campaign_brand.eq('测试品牌').all())
        self.assertTrue(csv.portfolio_spent_usd.eq(result.metrics['spent_usd']).all())
        self.assertAlmostEqual(csv.projected_conversions.sum(), result.metrics['conversions'])
        self.assertTrue(csv.simulation_notice.str.contains('SIMULATED').all())
        self.assertTrue(csv.selection_reason.notna().all())

    def test_cent_costs_and_validation(self):
        data = self.data.iloc[:2].assign(estimated_fee_usd=100.01)
        self.assertEqual(len(optimize_portfolio(data, 200.01).selected), 1)
        self.assertEqual(len(optimize_portfolio(data, 200.02).selected), 2)
        result = optimize_portfolio(data.iloc[:1], 200, sample_usd=10.10, shipping_usd=20.20)
        self.assertEqual(result.metrics['spent_usd'], 130.31)
        for value in (-1, float('nan'), float('inf'), 1.001):
            with self.assertRaises(ValueError):
                cents(value)

    def test_export_rejects_empty_and_preserves_safe_text(self):
        with self.assertRaisesRegex(ValueError, 'No recommended creators'):
            export_portfolio_csv(optimize_portfolio(self.data, 0), {})
        content = export_portfolio_csv(optimize_portfolio(self.data, 1000), {'brand': '=1+1'})
        self.assertTrue(pd.read_csv(BytesIO(content)).campaign_brand.eq("'=1+1").all())

    def test_deterministic_ties(self):
        data = pd.concat([self.data.iloc[[0]]] * 2, ignore_index=True)
        data['creator_id'] = ['B', 'A']
        result = optimize_portfolio(data, 280)
        self.assertEqual(result.selected.creator_id.tolist(), ['A'])


if __name__ == '__main__':
    unittest.main()
