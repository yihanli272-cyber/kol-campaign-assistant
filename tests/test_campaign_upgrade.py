from pathlib import Path
import unittest
import copy
from streamlit.testing.v1 import AppTest
from creator_registry import load_registry
from sprint_research import screen_accounts
from sprint_decision import adapt_model,run_plan
from campaign_upgrade import load_supplement,force_include,effect_scenario,score_v2

class UpgradeTests(unittest.TestCase):
 def setUp(self):
  self.t=load_registry(); self.s=screen_accounts(self.t['accounts']); self.m=adapt_model(self.t,self.s,True)
 def test_screenshot_match_separate_and_missing_preserved(self):
  d=load_supplement(self.t['accounts']); self.assertEqual(d.hicreator_match_rate.notna().sum(),2)
  self.assertTrue(d.set_index('creator_id').loc[['KOL-001','KOL-002'],'hicreator_match_rate'].eq(1).all())
  self.assertTrue(d.representative_posts.isna().all())
  v=score_v2(self.t,self.s,'Conversion',self.m,d)
  self.assertTrue(v['商业适配度'].isna().all()); self.assertTrue(v.total_score.isna().all())
 def test_force_is_budget_feasible_and_best_constrained_choice(self):
  base=run_plan(self.m); omitted=self.m.loc[~self.m.creator_id.isin(base.selected.creator_id)].iloc[0].creator_id
  before=self.m.copy(deep=True); a,b=force_include(self.m,omitted)
  self.assertIn(omitted,set(b.selected.creator_id)); self.assertLessEqual(b.metrics['spent_usd'],5000)
  self.assertLessEqual(b.metrics['creator_count'],6); self.assertLessEqual(b.metrics['target_reach'],a.metrics['target_reach'])
  import pandas as pd
  pd.testing.assert_frame_equal(before,self.m)
 def test_force_rejects_unqualified_and_overbudget(self):
  with self.assertRaises(ValueError): force_include(self.m,'KOL-001')
  with self.assertRaises(ValueError): force_include(self.m,self.m.iloc[0].creator_id,1)
 def test_fixed_reforecast_changes_metrics_not_membership(self):
  a,f,o=effect_scenario(self.m,5000,'Conversion',.5,.03,.005,.01)
  self.assertEqual(set(a.selected.creator_id),set(f.selected.creator_id))
  self.assertAlmostEqual(f.metrics['conversions']/a.metrics['conversions'],.125)
 def test_ui_controls_snapshots_and_formal_empty(self):
  a=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'),default_timeout=90).run(); self.assertFalse(a.exception)
  a.radio(key='presentation_mode').set_value('Research Workspace').run()
  a.number_input(key='effect_reach').set_value(.5).run(); self.assertFalse(a.exception)
  a.button(key='effect_save').click().run(); self.assertEqual(len(a.session_state['campaign_v2_snapshots']),1)
  saved=copy.deepcopy(a.session_state['campaign_v2_snapshots'])
  a.number_input(key='effect_ctr').set_value(.5).run(); self.assertEqual(a.session_state['campaign_v2_snapshots'],saved)
  a.radio(key='sprint_mode').set_value('正式推荐（仅已批准）').run(); self.assertFalse(a.exception)
if __name__=='__main__': unittest.main()


class MinimalConfigTests(unittest.TestCase):
 def test_petkit_config_and_baseline_metadata(self):
  import json
  a=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'),default_timeout=90).run()
  self.assertFalse(a.exception)
  self.assertEqual(a.text_input(key='campaign_brand').value,'PETKIT')
  self.assertEqual(a.text_input(key='campaign_product').value,'YumShare Dual-hopper 2')
  self.assertEqual(a.text_input(key='campaign_market').value,'United States')
  a.radio(key='presentation_mode').set_value('Research Workspace').run()
  a.number_input(key='effect_reach').set_value(.5)
  a.selectbox(key='sprint_assumption').set_value('Conservative').run()
  self.assertFalse(a.exception)
  frames=next(d.value for d in a.dataframe if 'baseline_parameters' in d.value and '计算' in d.value)
  base=frames.loc[frames['计算'].eq('原基准')].iloc[0]
  self.assertEqual(base.reach_multiplier,1)
  self.assertEqual(base.assumed_er,'未提供') # UI-only missing-value label; raw model retains null
  self.assertEqual(json.loads(base.baseline_parameters)[0]['assumed_ctr'],.005)
  changed=frames.loc[frames['计算'].eq('固定组合重算')].iloc[0]
  self.assertEqual(changed.reach_multiplier,.5)
  a.text_input(key='campaign_description').set_value('双仓智能干粮喂食器：定时定量喂养').run()
  self.assertFalse(a.exception)
  a.radio(key='sprint_mode').set_value('正式推荐（仅已批准）').run()
  self.assertFalse(a.exception)
  self.assertEqual(next(m.value for m in a.metric if m.label=='入选人数'),'0')
 def test_match_field_is_optional(self):
  from tempfile import TemporaryDirectory
  t=load_registry();d=load_supplement(t['accounts'])
  with TemporaryDirectory() as tmp:
   p=Path(tmp)/'supplement.csv';d.drop(columns=['hicreator_match_rate']).to_csv(p,index=False)
   self.assertTrue(load_supplement(t['accounts'],p).hicreator_match_rate.isna().all())

class ConfigImportTests(unittest.TestCase):
 def test_config_roundtrip_and_defaults_unchanged(self):
  import json
  import io
  from unittest.mock import patch
  import sprint_ui
  p=Path(__file__).resolve().parents[1]/'campaign_config.json'
  original=p.read_bytes()
  data=json.loads(original);data.update(budget_usd=3000,objective='Engagement')
  raw=json.dumps(data,ensure_ascii=False).encode('utf-8')
  state={'campaign_config_upload':io.BytesIO(raw)}
  with patch.object(sprint_ui.st,'session_state',state): sprint_ui.import_campaign_config()
  self.assertEqual(state['campaign_brand'],'PETKIT')
  self.assertEqual(state['campaign_product'],'YumShare Dual-hopper 2')
  self.assertEqual(state['sprint_budget'],3000)
  self.assertEqual(state['sprint_objective'],'Engagement')
  self.assertEqual(p.read_bytes(),original)
  self.assertNotIn('creator_registry_directory',sprint_ui.parse_campaign_config(raw))
 def test_invalid_upload_is_atomic(self):
  import io
  from unittest.mock import patch
  import sprint_ui
  for raw in [b'bad json',b'[]',b'{}',b'x'*65537]:
   state={'campaign_config_upload':io.BytesIO(raw),'campaign_brand':'PETKIT','sprint_budget':5000}
   with patch.object(sprint_ui.st,'session_state',state): sprint_ui.import_campaign_config()
   self.assertEqual(state['campaign_brand'],'PETKIT');self.assertEqual(state['sprint_budget'],5000)
   self.assertIn('campaign_import_error',state)
 def test_session_rerun_retains_petkit_edits_and_new_session_uses_defaults(self):
  path=str(Path(__file__).resolve().parents[1]/'app.py')
  a=AppTest.from_file(path,default_timeout=90).run()
  a.text_input(key='campaign_selling_points').set_value('双仓储粮、定时定量')
  a.number_input(key='sprint_budget').set_value(3000).run()
  a.run();self.assertFalse(a.exception)
  self.assertEqual(a.number_input(key='sprint_budget').value,3000)
  self.assertEqual(a.text_input(key='campaign_selling_points').value,'双仓储粮、定时定量')
  fresh=AppTest.from_file(path,default_timeout=90).run()
  self.assertFalse(fresh.exception)
  self.assertEqual(fresh.number_input(key='sprint_budget').value,5000)
  self.assertEqual(fresh.text_input(key='campaign_brand').value,'PETKIT')

class PriorityDisplayTests(unittest.TestCase):
 def test_priority_statuses_do_not_change_approval_or_sources(self):
  import pandas as pd
  from creator_registry import audit_registry
  from sprint_ui import priority_creator_view, PRIORITY_IDS
  t=load_registry();original=copy.deepcopy(t);s=screen_accounts(t['accounts'])
  v=priority_creator_view(t,s,audit_registry(t)).set_index('creator_id')
  self.assertEqual(v.index.tolist(),list(PRIORITY_IDS))
  self.assertEqual(v.platform.value_counts().to_dict(),{'Instagram':2,'TikTok':2,'YouTube':2})
  self.assertTrue(v.intake_status.eq('已接入').all())
  self.assertTrue(v.screening_status.eq('已完成初筛').all())
  self.assertTrue(v.research_status.eq('重点研究对象').all())
  self.assertTrue(v.human_review_status.eq('待审核').all())
  self.assertFalse(v.model_eligible.any())
  self.assertEqual(v.loc['KOL-006','content_status'],'已找到线索，待核实')
  self.assertEqual(v.loc['KOL-022','content_status'],'待补充证据')
  self.assertFalse(v.content_status.eq('已核验').any())
  for key in t:pd.testing.assert_frame_equal(t[key],original[key])
 def test_human_status_and_evidence_do_not_imply_model_eligibility(self):
  from creator_registry import audit_registry,STAGES
  from sprint_ui import priority_creator_view
  t=load_registry();s=screen_accounts(t['accounts']);audit=audit_registry(t)
  mask=t['reviews'].creator_id.eq('KOL-014')
  for stage in STAGES:t['reviews'].loc[mask,stage+'_status']='approved'
  v=priority_creator_view(t,s,audit).set_index('creator_id')
  self.assertEqual(v.loc['KOL-014','human_review_status'],'已通过')
  self.assertFalse(v.loc['KOL-014','model_eligible'])
  t['reviews'].loc[mask,'fit_status']='rejected'
  v=priority_creator_view(t,s,audit).set_index('creator_id')
  self.assertEqual(v.loc['KOL-014','human_review_status'],'未通过')

class VisualizationTests(unittest.TestCase):
 def test_chart_omits_missing_but_preserves_observed_zero(self):
  import pandas as pd
  from unittest.mock import patch
  from ui_layout import value_chart
  frame=pd.DataFrame({'达人':['A','B'],'值':[None,0.]});before=frame.copy(deep=True)
  with patch('ui_layout.st') as ui:
   value_chart(frame,'达人','值','第三方指标','次')
   shown=ui.vega_lite_chart.call_args.args[0]
   self.assertEqual(shown['达人'].tolist(),['B']);self.assertEqual(shown['值'].tolist(),[0.])
  pd.testing.assert_frame_equal(frame,before)
 def test_incomplete_radar_has_no_closed_score_polygon(self):
  from unittest.mock import patch
  from ui_layout import comparison_charts
  from sprint_research import score_registry,DIMENSIONS
  from creator_registry import load_registry
  t=load_registry();s=screen_accounts(t['accounts']);m=adapt_model(t,s,True)
  scores=score_registry(t,s,model=m)
  with patch('ui_layout.st') as ui:
   comparison_charts(t['accounts'],scores,['KOL-003','KOL-006'],DIMENSIONS)
   spec=ui.vega_lite_chart.call_args.args[0]
   self.assertFalse(any(layer.get('encoding',{}).get('detail',{}).get('field')=='达人' for layer in spec['layer']))
   self.assertTrue(any('未提供' in str(c) for c in ui.caption.call_args_list))


class ShowcasePresentationTests(unittest.TestCase):
 def test_missing_value_formatter_preserves_zero(self):
  from sprint_ui import display_value
  for value in [None,float('nan'),'','None','NaN']:
   self.assertEqual(display_value(value),'未提供')
  self.assertEqual(display_value(0),'0')
 def test_default_showcase_and_research_mode_keep_data_and_selection(self):
  a=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=90).run()
  self.assertFalse(a.exception)
  self.assertEqual(a.radio(key='presentation_mode').value,'Demo Showcase')
  self.assertTrue(any('六位重点候选' in h.value for h in a.subheader))
  self.assertTrue(any(m.label=='Selected Creators' for m in a.metric))
  a.radio(key='presentation_mode').set_value('Research Workspace').run()
  self.assertFalse(a.exception)
  self.assertTrue(any(m.label=='已使用预算（美元）' for m in a.metric))
  self.assertTrue(any(len(d.value)==52 and 'categories' in d.value for d in a.dataframe))
