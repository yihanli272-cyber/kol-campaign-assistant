import unittest
from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from creator_registry import load_registry
from showcase_ui import discovery_records, filter_discovery, demo_model
from sprint_research import screen_accounts


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables=load_registry()
        cls.records=discovery_records(cls.tables['accounts'])

    def test_all_52_stable_ids_and_platform_counts(self):
        self.assertEqual(len(self.records),52)
        self.assertEqual(set(self.records.creator_id),{f'KOL-{i:03d}' for i in range(1,53)})
        self.assertFalse(self.records.creator_id.duplicated().any())
        self.assertFalse(self.records.duplicated(['platform','handle']).any())
        self.assertEqual(self.records.groupby('platform').size().to_dict(),{'Instagram':20,'TikTok':20,'YouTube':12})

    def test_original_metrics_identity_and_optional_match_mapping(self):
        original=self.tables['accounts'].copy(deep=True)
        public=discovery_records(self.tables['accounts']).set_index('creator_id')
        for field in ['platform','handle','profile_url','reported_followers','reported_mean_views','reported_median_views','reported_mean_engagement_rate']:
            pd.testing.assert_series_equal(public[field],original.set_index('creator_id')[field])
        self.assertEqual(set(public.loc[public.match_rate.notna()].index),{'KOL-001','KOL-002'})
        self.assertTrue(public.loc[['KOL-001','KOL-002'],'match_rate'].eq(1).all())
        self.assertEqual(public.match_rate.isna().sum(),50)
        pd.testing.assert_frame_equal(original,self.tables['accounts'])
        self.assertFalse(any(c in public for c in ['data_source','evidence_source','source_file','human_status','email']))

    def test_literal_case_insensitive_search_and_platform_filter(self):
        self.assertEqual(len(filter_discovery(self.records,'TikTok')),20)
        self.assertEqual(filter_discovery(self.records,query='@PONYOANDLUNA').creator_id.tolist(),['KOL-001'])
        self.assertEqual(filter_discovery(self.records,'YouTube','KOL-041').creator_id.tolist(),['KOL-041'])
        self.assertTrue(filter_discovery(self.records,'TikTok','KOL-041').empty)
        self.assertTrue(filter_discovery(self.records,query='[').empty)

    def test_pagination_covers_all_records_and_shortlist_is_unchanged(self):
        seen=[]
        for offset in range(0,len(self.records),6):seen.extend(self.records.iloc[offset:offset+6].creator_id)
        self.assertEqual(len(seen),52);self.assertEqual(len(set(seen)),52)
        model,_=demo_model(self.tables,screen_accounts(self.tables['accounts']))
        self.assertEqual(set(model.creator_id),{'KOL-014','KOL-006','KOL-025','KOL-022','KOL-041','KOL-044'})

    def test_discovery_page_search_and_filters_do_not_change_campaign(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=90).run()
        self.assertFalse(app.exception)
        self.assertIn('Creator Discovery',[tab.label for tab in app.tabs])
        metric=lambda:next(m.value for m in app.metric if m.label=='Estimated Reach · Simulation')
        baseline=metric()
        app.selectbox(key='discovery_page').set_value(9).run()
        self.assertFalse(app.exception)
        app.text_input(key='discovery_query').set_value('KOL-041').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key='discovery_page').value,1)
        self.assertTrue(any('符合条件 1 条' in e.value for e in app.caption))
        app.selectbox(key='discovery_platform').set_value('TikTok').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('没有符合当前条件' in e.value for e in app.info))
        self.assertEqual(metric(),baseline)
