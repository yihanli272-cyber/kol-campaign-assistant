from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from creator_registry import load_registry
from sprint_research import screen_accounts
from showcase_ui import demo_model, scenario_results
from guided_trial_ui import initialize, open_trial, move_step, leave_trial, trial_results

ROOT=Path(__file__).resolve().parents[1]


class GuidedTrialTests(unittest.TestCase):
    def test_state_initialization_and_navigation_do_not_change_defaults(self):
        defaults=json.loads((ROOT/'campaign_config.json').read_text(encoding='utf-8'))
        before=deepcopy(defaults)
        with patch('guided_trial_ui.st') as ui:
            ui.session_state={}
            parameters=initialize(defaults)
            self.assertEqual(parameters['brand'],'PETKIT')
            self.assertEqual(parameters['budget'],5000)
            self.assertEqual(parameters['objective'],'Brand Awareness')
            self.assertEqual(parameters['level'],'基准')
            open_trial();self.assertTrue(ui.session_state['trial_active'])
            parameters['budget']=3000
            ui.session_state['discovery_query']='@meowscato'
            move_step(4)
            self.assertEqual(ui.session_state['trial_views']['discovery_query'],'@meowscato')
            self.assertEqual(initialize(defaults)['budget'],3000)
            move_step(99);self.assertEqual(ui.session_state['trial_step'],7)
            leave_trial();self.assertFalse(ui.session_state['trial_active'])
            self.assertEqual(parameters['budget'],3000)
        self.assertEqual(defaults,before)

    def test_selected_assumptions_are_existing_scenario_results(self):
        tables=load_registry();screen=screen_accounts(tables['accounts'])
        before={k:v.copy(deep=True) for k,v in tables.items()}
        model,_=demo_model(tables,screen)
        _,_,_,effects=scenario_results(model,3000,'Conversion')
        for label,_,_,expected in effects:
            *_,actual=trial_results(tables,screen,{'budget':3000,'objective':'Conversion','level':label})
            self.assertEqual(actual.metrics,expected.metrics)
            pd.testing.assert_frame_equal(actual.selected,expected.selected)
        for key in before:pd.testing.assert_frame_equal(tables[key],before[key])

    def test_all_seven_steps_preserve_parameters_and_expert_workspace(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=90).run()
        app.number_input(key='sprint_budget').set_value(4300).run()
        app.selectbox(key='sprint_objective').set_value('Engagement').run()
        original_budget=app.number_input(key='sprint_budget').value
        app.button(key='open_guided_trial').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Step 1 / 7' in e.value for e in app.subheader))
        app.button(key='trial_start').click().run()
        self.assertEqual(app.number_input(key='trial_budget_widget').value,5000)
        app.number_input(key='trial_budget_widget').set_value(3000).run()
        app.button(key='trial_continue').click().run()
        app.selectbox(key='discovery_platform').set_value('TikTok').run()
        app.text_input(key='discovery_query').set_value('@meowscato').run()
        app.button(key='trial_continue').click().run()
        self.assertTrue(any('Step 4 / 7' in e.value for e in app.subheader))
        app.button(key='trial_previous').click().run()
        self.assertEqual(app.selectbox(key='discovery_platform').value,'TikTok')
        self.assertEqual(app.text_input(key='discovery_query').value,'@meowscato')
        app.button(key='trial_continue').click().run()
        app.button(key='trial_continue').click().run()
        self.assertTrue(any('Step 5 / 7' in e.value for e in app.subheader))
        app.button(key='trial_continue').click().run()
        self.assertEqual(app.number_input(key='trial_budget_widget').value,3000)
        app.number_input(key='trial_budget_widget').set_value(7000).run()
        app.selectbox(key='trial_objective_widget').set_value('Conversion').run()
        app.selectbox(key='trial_level_widget').set_value('乐观').run()
        app.button(key='trial_continue').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Step 7 / 7' in e.value for e in app.subheader))
        params=deepcopy(app.session_state['trial_parameters'])
        self.assertEqual((params['budget'],params['objective'],params['level']),(7000,'Conversion','乐观'))
        t=load_registry();*_,expected=trial_results(t,screen_accounts(t['accounts']),params)
        self.assertEqual(next(m.value for m in app.metric if m.label=='模拟支出 · USD'),f"{expected.metrics['spent_usd']:,.2f}")
        self.assertEqual(len(app.get('download_button')),2)
        app.button(key='trial_previous').click().run()
        self.assertEqual(app.number_input(key='trial_budget_widget').value,7000)
        self.assertEqual(app.selectbox(key='trial_objective_widget').value,'Conversion')
        self.assertEqual(app.selectbox(key='trial_level_widget').value,'乐观')
        app.button(key='trial_continue').click().run()
        app.button(key='trial_finish').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key='sprint_budget').value,original_budget)
        self.assertEqual(app.selectbox(key='sprint_objective').value,'Engagement')
        self.assertIn('Creator Discovery',[tab.label for tab in app.tabs])
        self.assertEqual(app.session_state['trial_parameters']['budget'],7000)

    def test_welcome_explore_and_mid_trial_exit(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=90).run()
        app.button(key='open_guided_trial').click().run()
        app.button(key='trial_explore').click().run()
        self.assertFalse(app.session_state['trial_active'])
        app.button(key='open_guided_trial').click().run()
        app.button(key='trial_start').click().run()
        app.button(key='trial_exit').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state['trial_active'])
