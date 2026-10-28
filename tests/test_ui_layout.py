"""验证重新组织的工作台仍消费同一份计算结果。"""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from kol_data import load_kol_data
from portfolio import optimize_portfolio
from ui_layout import WORKSPACE_TABS


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceLayoutTests(unittest.TestCase):
    def open_app(self):
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
        self.assertFalse(app.exception)
        return app

    def test_sections_keep_single_existing_controls_and_result(self):
        app = self.open_app()
        self.assertEqual([tab.label for tab in app.tabs], WORKSPACE_TABS)
        self.assertEqual(len(app.tabs[1].multiselect), 2)
        self.assertEqual(len(app.multiselect), 2)
        self.assertEqual(len(app.tabs[3].button), 2)
        self.assertEqual(len(app.tabs[4].get('download_button')), 1)
        self.assertEqual(len(app.get('download_button')), 1)
        expected = optimize_portfolio(load_kol_data(), 5000)
        for index in (0, 2, 4):
            self.assertEqual(next(m.value for m in app.tabs[index].metric if m.label == '已使用预算（美元）'), f"{expected.metrics['spent_usd']:,.2f}")
        self.assertTrue(any(item.label == '执行成本与人数上限' for item in app.expander))

    def test_research_provenance_and_empty_state_survive_reorganization(self):
        app = self.open_app()
        app.radio(key='dataset').set_value('Real Creator Research Dataset').run()
        self.assertFalse(app.exception)
        tables = app.tabs[1].dataframe
        public = next(table.value for table in tables if 'verification_tier' in table.value)
        self.assertEqual(len(public), 30)
        self.assertTrue(public.verification_status.eq('部分核实').all())
        app.button(key='save_baseline').click().run()
        saved = app.session_state['baseline_research']
        app.multiselect[0].set_value([]).run()
        self.assertFalse(app.exception)
        self.assertTrue(any('没有可推荐' in item.value for item in app.tabs[0].info))
        self.assertTrue(any('没有创作者满足' in item.value for item in app.tabs[1].info))
        self.assertTrue(any('无可行组合' in item.value for item in app.tabs[3].warning))
        self.assertEqual(len(app.tabs[4].get('download_button')), 0)
        self.assertEqual(app.session_state['baseline_research'], saved)

    def test_home_entries_switch_existing_sections_without_losing_baseline(self):
        app = self.open_app()
        app.button(key='save_baseline').click().run()
        saved = app.session_state['baseline']
        for number, target in [('01', 'KOL 数据库'), ('02', '投放组合优化'),
                               ('03', '情景分析'), ('04', '报告与导出')]:
            app.button(key=f'go_module_{number}').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['workspace_view'], target)
            self.assertEqual(app.session_state['baseline'], saved)
            self.assertEqual(len(app.multiselect), 2)
            self.assertEqual(len(app.get('download_button')), 1)
        app.button(key='go_portfolio').click().run()
        self.assertEqual(app.session_state['workspace_view'], '投放组合优化')

    def test_detail_cards_keep_single_export_and_theme_matches_reference(self):
        app = self.open_app()
        keys = {item.key for item in app.get('flex_container')}
        # 布局卡片使用原生容器；不用自制 HTML 输入或额外框架。
        for section in ('database', 'portfolio', 'scenario', 'report'):
            self.assertIn(f'panel_{section}_main', keys)
            self.assertIn(f'panel_{section}_aside', keys)
        self.assertEqual(len(app.get('download_button')), 1)
        self.assertTrue(any('主要风险' in item.value for item in app.tabs[0].caption))
        import tomllib
        theme = tomllib.loads((ROOT / '.streamlit' / 'config.toml').read_text(encoding='utf-8'))['theme']
        self.assertEqual(theme['base'], 'light')
        self.assertEqual(theme['primaryColor'], '#163f3c')


if __name__ == '__main__':
    unittest.main()
