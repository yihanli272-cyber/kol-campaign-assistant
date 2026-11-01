"""Stage A data contracts; approval examples below are in-memory test fixtures only."""
from pathlib import Path
import tempfile
import unittest
import os
from unittest.mock import patch
from fixture_workbook import write_fixture_workbook, fixture_rows

import pandas as pd

from creator_registry import (FILES, REGISTRY_DIR, ACCOUNT_FIELDS, EVIDENCE_FIELDS,
    ASSUMPTION_FIELDS, PARAMETERS, STAGES, read_source_workbook, normalize_source,
    validate_registry, load_registry, audit_registry, import_workbook)


class CreatorRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tables = load_registry()

    def test_all_52_stable_records_platform_counts_and_source_provenance(self):
        accounts = self.tables['accounts']
        self.assertEqual(set(accounts.creator_id), {f'KOL-{i:03}' for i in range(1, 53)})
        self.assertEqual(accounts.platform.value_counts().to_dict(), {'Instagram': 20, 'TikTok': 20, 'YouTube': 12})
        self.assertTrue(accounts.data_source.eq('HiCreator 导出').all())
        self.assertTrue(accounts.export_date.eq('2026-10-30').all())
        self.assertTrue(accounts.metric_data_date.isna().all())
        self.assertTrue(accounts.identity_data_type.eq('third_party_reported').all())

    def test_round_trip_matches_read_only_source_import(self):
        with tempfile.TemporaryDirectory() as folder:
            path=write_fixture_workbook(Path(folder)/'synthetic_fixture.xlsx')
            normalized=validate_registry(normalize_source(read_source_workbook(path),path))
            for key,(name,_) in FILES.items():
                normalized[key].to_csv(Path(folder)/name,index=False)
            restored=load_registry(folder)
            for key in normalized:
                pd.testing.assert_frame_equal(normalized[key],restored[key],check_dtype=False)
            a=restored['accounts'].set_index('creator_id')
            self.assertEqual(len(a),3)
            self.assertTrue(pd.isna(a.loc['TEST-IG','creator_name']))
            self.assertTrue(pd.isna(a.loc['TEST-IG','reported_mean_engagement_rate']))
            self.assertEqual(a.loc['TEST-IG','reported_median_views'],12.5)
            self.assertEqual(a.loc['TEST-TT','reported_median_views'],0)

    def test_long_ids_remain_exact_text_and_risk_not_recovered(self):
        with tempfile.TemporaryDirectory() as folder:
            path=write_fixture_workbook(Path(folder)/'synthetic_fixture.xlsx')
            source=read_source_workbook(path)
            normalized=validate_registry(normalize_source(source,path))['accounts'].set_index('creator_id')
            for original in fixture_rows():
                self.assertEqual(normalized.loc[original['creator_id'],'platform_account_id'],original['platform_account_id'])
            self.assertEqual(normalized.loc['TEST-TT','account_id_precision_status'],'precision_loss_risk')
            self.assertEqual(normalized.loc['TEST-IG','account_id_precision_status'],'unverified')
        accounts = self.tables['accounts']
        for _, row in accounts.iterrows():
            self.assertIsInstance(row.platform_account_id, str)
        tiktok = accounts.loc[accounts.platform.eq('TikTok')]
        self.assertEqual(len(tiktok), 20)
        self.assertTrue(tiktok.account_id_precision_status.eq('precision_loss_risk').all())
        self.assertTrue(accounts.verified_platform_account_id.isna().all())
        self.tables['accounts'].loc[accounts.platform.eq('TikTok'), 'account_id_precision_status'] = 'unverified'
        with self.assertRaisesRegex(ValueError, '精度'):
            validate_registry(self.tables)

    def test_missing_values_and_fractional_source_statistics_preserved(self):
        a = self.tables['accounts'].set_index('creator_id')
        self.assertTrue(pd.isna(a.loc['KOL-019', 'creator_name']))
        self.assertTrue(pd.isna(a.loc['KOL-013', 'reported_mean_engagement_rate']))
        self.assertTrue(pd.isna(a.loc['KOL-013', 'reported_median_engagement_rate']))
        self.assertEqual(a.loc['KOL-001', 'reported_median_views'], 27006.5)
        self.assertAlmostEqual(a.loc['KOL-001', 'reported_mean_engagement_rate'], .04406822556297307)

    def test_duplicate_names_are_not_merged_and_entities_are_unlinked(self):
        a = self.tables['accounts']
        for first, second in [('KOL-006', 'KOL-044'), ('KOL-014', 'KOL-021'), ('KOL-017', 'KOL-033')]:
            pair = a.loc[a.creator_id.isin([first, second])]
            self.assertEqual(len(pair), 2)
            self.assertEqual(pair.platform.nunique(), 2)
        self.assertTrue(a.entity_id.isna().all())
        self.assertTrue(a.entity_link_status.eq('pending').all())

    def test_entity_link_requires_manual_evidence_reviewer_and_date(self):
        self.tables['accounts'].loc[0, 'entity_id'] = 'ENTITY-TEST'
        with self.assertRaisesRegex(ValueError, '主体关联'):
            validate_registry(self.tables)
        self.tables['accounts'].loc[0, ['entity_link_status', 'entity_link_evidence',
            'entity_link_checked_by', 'entity_link_checked_at']] = ['verified', 'manual test evidence', 'test reviewer', '2026-10-30']
        self.assertEqual(validate_registry(self.tables)['accounts'].loc[0, 'entity_id'], 'ENTITY-TEST')

    def test_region_never_becomes_audience_share(self):
        a = self.tables['accounts']
        self.assertTrue(a.creator_region.eq('美国').all())
        self.assertTrue(a.us_audience_share.isna().all())
        self.tables['accounts'].loc[0, 'us_audience_share'] = .8
        with self.assertRaisesRegex(ValueError, '美国受众'):
            validate_registry(self.tables)

    def test_subject_hints_are_not_approval(self):
        a = self.tables['accounts'].set_index('creator_id')
        self.assertEqual(a.loc['KOL-047', 'subject_type_hint'], 'brand_channel_reported')
        self.assertEqual(a.loc['KOL-052', 'subject_type_hint'], 'manufacturer_reported')
        self.assertEqual(a.subject_type_hint.eq('unknown').sum(), 50)
        self.assertTrue(a.confirmed_subject_type.isna().all())
        self.assertTrue(self.tables['reviews'].subject_type_status.eq('pending').all())

    def test_no_fabricated_evidence_or_assumptions(self):
        self.assertTrue(self.tables['evidence'].empty)
        self.assertTrue(self.tables['assumptions'].empty)
        self.assertTrue(set(EVIDENCE_FIELDS).issubset(self.tables['evidence'].columns))
        self.assertTrue(set(ASSUMPTION_FIELDS).issubset(self.tables['assumptions'].columns))
        self.assertFalse(set(PARAMETERS) & set(self.tables['accounts'].columns))
        # Contact/demographic data remains in the original workbook, not this app registry.
        self.assertNotIn('email', self.tables['accounts'])

    def test_review_progress_and_formal_pool_initially_empty(self):
        for stage in STAGES:
            self.assertTrue(self.tables['reviews'][f'{stage}_status'].eq('pending').all())
            self.assertTrue(self.tables['reviews'][f'{stage}_reason'].notna().all())
        audit = audit_registry(self.tables)
        self.assertEqual(len(audit), 52)
        self.assertEqual(audit.model_eligible.sum(), 0)
        self.assertTrue(audit.pending_reasons.str.len().gt(0).all())

    def test_approval_flag_alone_cannot_enable_model(self):
        r = self.tables['reviews']
        for stage in STAGES:
            r.loc[0, [f'{stage}_status', f'{stage}_reason', f'{stage}_checked_by', f'{stage}_checked_at']] = ['approved', 'test-only approval', 'test reviewer', '2026-10-30']
        audit = audit_registry(self.tables)
        self.assertFalse(audit.loc[0, 'model_eligible'])
        self.assertIn('内容证据', audit.loc[0, 'pending_reasons'])
        self.assertIn('投放假设', audit.loc[0, 'pending_reasons'])

    def test_approved_stages_require_reviewer_and_date(self):
        self.tables['reviews'].loc[0, 'identity_status'] = 'approved'
        with self.assertRaisesRegex(ValueError, '审核人'):
            validate_registry(self.tables)

    def test_complete_test_fixture_can_pass_but_brand_subject_is_held(self):
        # These are invented test inputs in memory, never written to the registry.
        r = self.tables['reviews']
        for stage in STAGES:
            r.loc[0, [f'{stage}_status', f'{stage}_reason', f'{stage}_checked_by', f'{stage}_checked_at']] = ['approved', 'unit-test fixture', 'test reviewer', '2026-10-30']
        self.tables['accounts'].loc[0, 'confirmed_subject_type'] = 'creator'
        evidence = dict.fromkeys(EVIDENCE_FIELDS, '')
        evidence.update(evidence_id='TEST-E1', creator_id='KOL-001', platform='Instagram',
            post_url='https://www.instagram.com/p/TEST_FIXTURE/', post_date='2026-10-29',
            content_format='short_video', content_topic='test fixture', evidence_source='test-only manual record',
            checked_at='2026-10-30', verification_status='verified', product_relevance_reason='test-only reason')
        self.tables['evidence'] = pd.DataFrame([evidence])
        params = dict.fromkeys(ASSUMPTION_FIELDS, '')
        params.update(creator_id='KOL-001', platform='Instagram', content_format='short_video',
            model_data_type='simulated', assumption_version='unit-test-v1', assumption_status='approved',
            planning_basis='test fixture', engagement_rate_basis='reach', checked_by='test reviewer', checked_at='2026-10-30')
        for field in PARAMETERS:
            params[field] = {'estimated_fee_usd': 500, 'estimated_reach': 10000,
                'assumed_audience_match_score': 70, 'assumed_content_quality_score': 70}.get(field, .02)
            params[field + '_source'] = 'simulated unit-test fixture'
        self.tables['assumptions'] = pd.DataFrame([params])
        audit = audit_registry(self.tables)
        self.assertTrue(audit.loc[0, 'model_eligible'])
        self.assertEqual(audit.loc[0, 'review_progress'], '具备投放模型资格')
        self.tables['accounts'].loc[0, 'confirmed_subject_type'] = 'brand_channel'
        self.assertFalse(audit_registry(self.tables).loc[0, 'model_eligible'])

    def test_unknown_and_duplicate_ids_and_missing_fields_rejected(self):
        for key, value in [('creator_id', 'KOL-002'), ('platform', 'Other')]:
            tables = {k: v.copy() for k, v in self.tables.items()}
            tables['accounts'].loc[0, key] = value
            with self.assertRaises(ValueError):
                validate_registry(tables)
        self.tables['accounts'] = self.tables['accounts'].drop(columns=['platform_account_id'])
        with self.assertRaisesRegex(ValueError, '必要字段'):
            validate_registry(self.tables)

    def test_evidence_references_and_metrics_are_validated(self):
        pending = dict.fromkeys(EVIDENCE_FIELDS, '')
        pending.update(evidence_id='TEST-E1', creator_id='KOL-001', platform='TikTok', verification_status='pending')
        self.tables['evidence'] = pd.DataFrame([pending])
        with self.assertRaisesRegex(ValueError, '平台'):
            validate_registry(self.tables)
        self.tables['evidence'].loc[0, 'platform'] = 'Instagram'
        self.tables['evidence'].loc[0, 'visible_views'] = '-1'
        with self.assertRaisesRegex(ValueError, '数值'):
            validate_registry(self.tables)
        self.tables['evidence'].loc[0, 'visible_views'] = '0'
        valid = validate_registry(self.tables)
        self.assertEqual(valid['evidence'].loc[0, 'visible_views'], 0)
        self.assertTrue(pd.isna(valid['evidence'].loc[0, 'visible_likes']))
        self.tables['evidence'].loc[0, 'verification_status'] = 'verified'
        with self.assertRaisesRegex(ValueError, '原帖'):
            validate_registry(self.tables)

    def test_assumptions_are_simulated_and_not_observed(self):
        row = dict.fromkeys(ASSUMPTION_FIELDS, '')
        row.update(creator_id='KOL-001', platform='Instagram', model_data_type='observed', assumption_status='pending')
        self.tables['assumptions'] = pd.DataFrame([row])
        with self.assertRaisesRegex(ValueError, 'simulated'):
            validate_registry(self.tables)
        self.tables['assumptions'].loc[0, 'model_data_type'] = 'simulated'
        self.tables['assumptions'].loc[0, 'assumption_status'] = 'approved'
        with self.assertRaisesRegex(ValueError, '完整参数'):
            validate_registry(self.tables)

    def test_real_and_simulated_parameters_cannot_mix(self):
        self.tables['accounts']['assumed_ctr'] = .02
        with self.assertRaisesRegex(ValueError, '混入'):
            validate_registry(self.tables)

    def test_reimport_refuses_overwrite(self):
        before = (REGISTRY_DIR / 'accounts.csv').read_bytes()
        with patch.dict(os.environ,{'KOL_DEPLOYMENT_MODE':'local_dev'}):
            with patch('creator_registry.read_source_workbook'), patch('creator_registry.normalize_source',return_value=self.tables):
                with self.assertRaises(FileExistsError):
                    import_workbook(path=Path('synthetic_fixture.xlsx'))
        self.assertEqual(before, (REGISTRY_DIR / 'accounts.csv').read_bytes())

    def test_read_error_is_clear_and_input_is_not_mutated(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, '无法读取'):
                load_registry(Path(folder))
        before = self.tables['accounts'].copy(deep=True)
        audit_registry(self.tables)
        pd.testing.assert_frame_equal(before, self.tables['accounts'])


if __name__ == '__main__':
    unittest.main()
