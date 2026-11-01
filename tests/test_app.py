from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class AppSmokeTests(unittest.TestCase):
    def test_research_without_any_eligible_model_inputs(self):
        from research_data import load_campaign_assumptions
        disabled = load_campaign_assumptions().assign(model_enabled=False)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "legacy_app.py"), default_timeout=30).run()
        with patch('research_data.load_campaign_assumptions', return_value=disabled):
            app.radio(key='dataset').set_value('Real Creator Research Dataset').run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any(metric.label == '模型参数完整的候选' and metric.value == '0' for metric in app.metric))
        self.assertEqual(len(app.get('download_button')), 0)
        self.assertTrue(app.button(key='save_baseline').disabled)

    def test_research_switch_planning_and_separate_baselines(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "legacy_app.py"), default_timeout=30).run()
        app.button(key="save_baseline").click().run()
        demo_baseline = app.session_state['baseline']
        app.radio(key='dataset').set_value('Real Creator Research Dataset').run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any(metric.label == '研究候选身份' and metric.value == '30' for metric in app.metric))
        self.assertTrue(any(metric.label == '模型参数完整的候选' and metric.value == '5' for metric in app.metric))
        self.assertTrue(any('真实身份＋模拟规划' in item.value for item in app.warning))
        self.assertEqual(len(app.get('download_button')), 1)
        app.button(key='save_baseline').click().run()
        self.assertEqual(app.session_state['baseline_research']['campaign']['dataset'], 'Real Creator Research Dataset')
        budget = next(widget for widget in app.number_input if widget.label == '模拟总预算（美元）')
        budget.set_value(1000).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any(metric.label == '已使用预算（美元）' and metric.value == '1,000.00' for metric in app.metric))
        self.assertEqual(app.session_state['baseline_research']['metrics']['budget_usd'], 5000)
        followers = next(widget for widget in app.number_input if widget.label == '最低粉丝数')
        followers.set_value(1000).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.get('download_button')), 0)
        app.radio(key='dataset').set_value('Simulated Demo Dataset').run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state['baseline'], demo_baseline)
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == '模拟创作者'), '30')

    def test_budget_baseline_and_download_flow(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "legacy_app.py"), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        app.button(key="save_baseline").click().run()
        saved = app.session_state["baseline"]
        self.assertEqual(saved["metrics"]["budget_usd"], 5000)
        self.assertTrue(any("输入未变化" in item.value for item in app.info))
        budget = next(widget for widget in app.number_input if widget.label == "模拟总预算（美元）")
        budget.set_value(3000).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["baseline"], saved)
        self.assertTrue(any(metric.label == "总预算（美元）" and metric.value == "3,000.00" for metric in app.metric))
        self.assertEqual(len(app.get("download_button")), 1)
        budget = next(widget for widget in app.number_input if widget.label == "模拟总预算（美元）")
        budget.set_value(0).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("无可行组合" in item.value for item in app.warning))
        self.assertEqual(len(app.get("download_button")), 0)
        app.button(key="clear_baseline").click().run()
        with self.assertRaises(KeyError):
            app.session_state["baseline"]

    def test_default_objective_and_empty_filter(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "legacy_app.py"), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "模拟创作者"), "30")
        app.selectbox[0].select("Conversion").run()
        self.assertEqual(len(app.exception), 0)
        app.multiselect[0].set_value([]).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("没有创作者满足" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
