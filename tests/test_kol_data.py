import tempfile
import unittest
from pathlib import Path

import pandas as pd

from kol_data import REQUIRED_FIELDS, RANGES, WEIGHTS, load_kol_data, score_kols, validate_kol_data


class KolDataTests(unittest.TestCase):
    def setUp(self):
        self.data = load_kol_data()

    def test_csv_has_30_records_and_required_fields(self):
        self.assertEqual(len(self.data), 30)
        self.assertTrue(set(REQUIRED_FIELDS).issubset(self.data.columns))
        self.assertEqual(self.data.platform.value_counts().to_dict(), {"Instagram": 15, "TikTok": 15})

    def test_key_values_are_in_range_and_simulated(self):
        for field, (lower, upper) in RANGES.items():
            self.assertTrue(self.data[field].between(lower, upper).all(), field)
        self.assertTrue(self.data.data_type.eq("simulated").all())
        self.assertTrue(self.data.creator_name.str.startswith("SIM ").all())

    def test_empty_data_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            validate_kol_data(self.data.iloc[:0])

    def test_missing_field_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Missing required fields: followers"):
            validate_kol_data(self.data.drop(columns="followers"))

    def test_bad_numeric_values_rejected(self):
        for field, value in (("followers", -1), ("estimated_fee_usd", 0), ("content_quality_score", 101), ("engagement_rate", float("nan")), ("estimated_reach", float("inf"))):
            data = self.data.copy().astype({field: float})
            data.loc[0, field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                validate_kol_data(data)

    def test_duplicate_ids_rejected(self):
        data = self.data.copy()
        data.loc[1, "creator_id"] = data.loc[0, "creator_id"]
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_kol_data(data)

    def test_blank_csv_has_read_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.csv"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unable to read KOL CSV"):
                load_kol_data(path)

    def test_known_scores_and_objective_weights(self):
        row = self.data.iloc[[0]].copy()
        row.loc[:, "audience_match_score"] = 100
        row.loc[:, "estimated_reach"] = 100000
        row.loc[:, "engagement_rate"] = 0.10
        row.loc[:, "content_quality_score"] = 100
        row.loc[:, "estimated_fee_usd"] = 1000
        row.loc[:, "assumed_ctr"] = 0.02
        row.loc[:, "assumed_click_to_purchase_cvr"] = 0.02
        for objective in WEIGHTS:
            with self.subTest(objective=objective):
                self.assertAlmostEqual(sum(WEIGHTS[objective].values()), 1)
                self.assertAlmostEqual(score_kols(row, objective).iloc[0].total_score, 100)
                self.assertTrue(score_kols(self.data, objective).total_score.between(0, 100).all())

    def test_score_does_not_change_with_candidate_filter(self):
        full = score_kols(self.data).set_index("creator_id")
        subset = score_kols(self.data.iloc[:5]).set_index("creator_id")
        pd.testing.assert_series_equal(full.loc[subset.index, "total_score"], subset.total_score)

    def test_deterministic_order_and_input_not_modified(self):
        before = self.data.copy(deep=True)
        pd.testing.assert_frame_equal(score_kols(self.data), score_kols(self.data.sample(frac=1, random_state=7)))
        pd.testing.assert_frame_equal(before, self.data)

    def test_unknown_objective_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown campaign objective"):
            score_kols(self.data, "Unknown")


if __name__ == "__main__":
    unittest.main()
