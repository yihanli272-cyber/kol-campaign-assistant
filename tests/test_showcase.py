import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from creator_registry import load_registry
from sprint_research import screen_accounts
from sprint_decision import run_plan, safe_csv
from campaign_upgrade import force_include, compare_results
from showcase_ui import demo_model, public_export, scenario_results


class ShowcaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables=load_registry()
        cls.screen=screen_accounts(cls.tables['accounts'])
        cls.model,cls.config=demo_model(cls.tables,cls.screen)
        cls.baseline,cls.budgets,cls.objectives,cls.effects=scenario_results(cls.model,5000,'Brand Awareness')

    def test_six_complete_deterministic_parameters(self):
        self.assertEqual(set(self.model.creator_id),{'KOL-014','KOL-006','KOL-025','KOL-022','KOL-041','KOL-044'})
        again,_=demo_model(self.tables,self.screen)
        pd.testing.assert_frame_equal(self.model,again)
        for field in ['estimated_fee_usd','estimated_reach','engagement_rate','assumed_ctr','assumed_click_to_purchase_cvr']:
            self.assertTrue(self.model[field].notna().all())
            self.assertGreater(self.model[field].nunique(),1)
        self.assertEqual(len(self.baseline.candidates),6)

    def test_history_and_reviews_not_overwritten(self):
        before={k:v.copy(deep=True) for k,v in self.tables.items()}
        demo_model(self.tables,self.screen)
        for key in before:pd.testing.assert_frame_equal(before[key],self.tables[key])
        original=self.tables['accounts'].set_index('creator_id')
        for r in self.model.itertuples():self.assertEqual(r.followers,original.loc[r.creator_id,'reported_followers'])

    def test_public_export_allowlist_no_provenance_contacts_or_review(self):
        frame=public_export(self.baseline,self.config,'Brand Awareness')
        contents=safe_csv(frame).decode('utf-8-sig')
        for token in ['HiCreator','hicreator','evidence_source','source_file','source_row','checked_by','email','@gmail','verification_status','pending','formal_eligibility']:
            self.assertNotIn(token,contents)
        self.assertIn('illustrative planning assumptions',contents)
        self.assertEqual(set(frame.loc[frame.selected,'creator_id']),set(self.baseline.selected.creator_id))
        self.assertEqual(frame.portfolio_spent_usd.iloc[0],self.baseline.metrics['spent_usd'])

    def test_budget_and_objective_use_existing_optimizer(self):
        for label,p in self.budgets:
            direct=run_plan(self.model,int(label.replace('$','').replace(',','')),'Brand Awareness')
            self.assertEqual(p.metrics,direct.metrics)
            self.assertEqual(p.selected.creator_id.tolist(),direct.selected.creator_id.tolist())
        for objective,p in self.objectives:self.assertEqual(p.metrics,run_plan(self.model,5000,objective).metrics)

    def test_fixed_membership_and_effect_formula(self):
        for label,factor,fixed,opt in self.effects:
            self.assertEqual(set(fixed.selected.creator_id),set(self.baseline.selected.creator_id))
            self.assertAlmostEqual(fixed.metrics['clicks'],self.baseline.metrics['clicks']*factor**2)
            self.assertAlmostEqual(fixed.metrics['conversions'],self.baseline.metrics['conversions']*factor**3)
            self.assertGreaterEqual(opt.metrics['target_reach'],fixed.metrics['target_reach'])

    def test_force_inclusion_and_all_deltas(self):
        omitted=next(c for c in self.model.creator_id if c not in set(self.baseline.selected.creator_id))
        before,after=force_include(self.model,omitted)
        self.assertIn(omitted,set(after.selected.creator_id))
        self.assertLessEqual(after.metrics['spent_usd'],5000)
        delta=compare_results(before,after).set_index('metric')
        for key in ['spent_usd','target_reach','engagements','clicks','conversions']:
            self.assertAlmostEqual(delta.loc[key,'delta'],after.metrics[key]-before.metrics[key])

    def test_empty_chart_hidden_zero_preserved(self):
        from ui_layout import value_chart
        with patch('ui_layout.st') as ui:
            value_chart(pd.DataFrame({'name':['A'],'value':[None]}),'name','value','Title','Unit')
            ui.vega_lite_chart.assert_not_called();ui.caption.assert_not_called()
            value_chart(pd.DataFrame({'name':['A'],'value':[0]}),'name','value','Title','Unit')
            self.assertEqual(ui.vega_lite_chart.call_args.args[0].value.iloc[0],0)

    def test_default_cards_clean_ui_and_no_wide_frames(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=90).run()
        self.assertFalse(app.exception)
        text='\n'.join(str(e.value) for name in ['markdown','caption','info','warning','subheader'] for e in getattr(app,name))
        for token in ['HiCreator','hicreator','待核验','资格不足','未提供','N/A','None','尚未取得原帖证据']:
            self.assertNotIn(token,text)
        for handle in ['itscookie.cat','girlsandtheircats','hangiefurbabies','meowscato','petopedia_','GirlsandTheirCats']:
            self.assertIn('@'+handle,text)
        self.assertEqual(len(app.dataframe),0)
        self.assertEqual(len(app.get('download_button')),4)

    def test_empty_platform_and_zero_budget_render(self):
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=90).run()
        app.multiselect(key='sprint_platforms').set_value([]).run()
        self.assertFalse(app.exception)
        app.number_input(key='sprint_budget').set_value(0).run()
        self.assertFalse(app.exception)

