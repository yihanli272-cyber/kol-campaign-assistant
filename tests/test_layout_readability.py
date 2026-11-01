"""Presentation regressions: canvas wrapping and chart/heading separation."""
import unittest
from unittest.mock import patch
import pandas as pd


class LayoutReadabilityTests(unittest.TestCase):
    def test_chart_title_outside_plot_and_padding_is_object(self):
        from ui_layout import value_chart
        frame=pd.DataFrame({'账号':['A','B'],'数值':[10,20],'组合':['入选','备选']})
        with patch('ui_layout.st') as ui:
            value_chart(frame,'账号','数值','中文 English 标题','人',group='组合',horizontal=True)
            spec=ui.vega_lite_chart.call_args.args[1]
            self.assertNotIn('title',spec)
            self.assertIsInstance(spec['padding'],dict)
            self.assertGreaterEqual(spec['height'],240)
            self.assertEqual(spec['encoding']['color']['legend']['orient'],'bottom')
            ui.markdown.assert_called_with('**中文 English 标题**')
            pd.testing.assert_frame_equal(ui.vega_lite_chart.call_args.args[0],frame)

    def test_shared_research_table_enables_wrapping_without_mutating_data(self):
        from sprint_ui import table
        frame=pd.DataFrame({'creator_id':['KOL-014'],'reason':['中英文 long text '*20]})
        before=frame.copy(deep=True)
        with patch('sprint_ui.st') as ui:
            table(frame)
            options=ui.dataframe.call_args.kwargs
            self.assertGreater(options['row_height'],64)
            self.assertEqual(options['height'],'auto')
        pd.testing.assert_frame_equal(frame,before)

    def test_legacy_table_also_has_readable_row_height(self):
        from ui_zh import show_table
        with patch('ui_zh.st') as ui:
            show_table(pd.DataFrame({'creator_id':['KOL-014']}))
            self.assertGreater(ui.dataframe.call_args.kwargs['row_height'],64)
            self.assertEqual(ui.dataframe.call_args.kwargs['height'],'auto')
