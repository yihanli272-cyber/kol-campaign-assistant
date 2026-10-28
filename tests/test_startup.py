"""Fresh-process import checks complement AppTest and HTTP server health checks."""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def run_fresh_python(self, source):
        result = subprocess.run(
            [sys.executable, "-B", "-c", source], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        return result.stdout

    def test_local_import_names_and_versions_in_fresh_process(self):
        output = self.run_fresh_python('''
import ast
import importlib
from pathlib import Path
import kol_data
import research_data
import portfolio

root = Path.cwd()
modules = {name: importlib.import_module(name) for name in ("kol_data", "research_data", "portfolio")}
for name, module in modules.items():
    assert Path(module.__file__).resolve() == root / (name + ".py"), module.__file__
for filename in ("app.py", "kol_data.py", "research_data.py", "portfolio.py"):
    tree = ast.parse((root / filename).read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in modules:
            for item in node.names:
                assert hasattr(modules[node.module], item.name), f"{filename}: missing {node.module}.{item.name}"
assert research_data.RESEARCH_ASSUMPTION_VERSION == kol_data.RESEARCH_ASSUMPTION_VERSION
assumptions = research_data.load_campaign_assumptions()
assert assumptions.assumption_version.eq(kol_data.RESEARCH_ASSUMPTION_VERSION).all()
print("Fresh imports, local paths and CSV version contract: OK")
''')
        self.assertIn("Fresh imports, local paths and CSV version contract: OK", output)

    def test_app_executes_both_datasets_in_fresh_process(self):
        output = self.run_fresh_python('''
from pathlib import Path
from streamlit.testing.v1 import AppTest

app = AppTest.from_file(str(Path.cwd() / "app.py"), default_timeout=30).run()
assert not app.exception, [item.message for item in app.exception]
assert next(item.value for item in app.metric if item.label == "模拟创作者") == "30"
app.radio(key="dataset").set_value("Real Creator Research Dataset").run()
assert not app.exception, [item.message for item in app.exception]
assert any(item.label == "模型参数完整的候选" and item.value == "5" for item in app.metric)
print("Fresh Streamlit script execution, both datasets: OK")
''')
        self.assertIn("Fresh Streamlit script execution, both datasets: OK", output)


if __name__ == "__main__":
    unittest.main()
