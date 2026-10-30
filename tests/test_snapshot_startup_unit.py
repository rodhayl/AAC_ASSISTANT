"""Offline checks of historical startup defaults, without starting servers/GUI."""
import ast
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class StartupDefaultsTests(unittest.TestCase):
    def test_launcher_default_and_explicit_config(self):
        import os
        tree = ast.parse((ROOT / "launcher.pyw").read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "load_config")
        namespace = {"os": os}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "launcher-config", "exec"), namespace)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(namespace["load_config"](tmp)["BACKEND_HOST"], "127.0.0.1")
            Path(tmp, "env.properties").write_text("BACKEND_HOST=192.0.2.1\n")
            self.assertEqual(namespace["load_config"](tmp)["BACKEND_HOST"], "192.0.2.1")

    def test_python_entrypoint_uses_config(self):
        tree = ast.parse((ROOT / "src/api/main.py").read_text())
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and ast.unparse(n.func) == "uvicorn.run")
        kw = {k.arg: ast.unparse(k.value) for k in call.keywords}
        self.assertEqual(kw["host"], "config.BACKEND_HOST")
        self.assertEqual(kw["port"], "config.BACKEND_PORT")

    def test_windows_source_defaults(self):
        start = (ROOT / "start.bat").read_text()
        self.assertIn('if not defined BACKEND_HOST set "BACKEND_HOST=127.0.0.1"', start)
        self.assertIn("--host %BACKEND_HOST%", start)
        for name in ("start.bat", "launcher.pyw", "install_dependencies.bat", "build_package.bat"):
            source = (ROOT / name).read_text()
            self.assertNotIn("0.0.0.0", source)
            self.assertNotIn("AAC_BOOTSTRAP_ADMIN_PASSWORD=Admin123", source)

if __name__ == "__main__":
    unittest.main()
