"""Focused JWT regression checks; no app startup, database, or network access.

Run: python -m unittest discover -s tests -p test_snapshot_jwt_unit.py -v
The module is loaded with an isolated configuration, not a real installation.
"""

import ast
import importlib.util
import secrets
import sys
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import jwt


ROOT = Path(__file__).resolve().parents[1]


class SnapshotJWTTests(unittest.TestCase):
    def setUp(self):
        self.key = secrets.token_hex(32)
        config = types.SimpleNamespace(get=lambda key, default=None: {
            "JWT_SECRET_KEY": self.key,
            "ENVIRONMENT": "development",
        }.get(key, default))
        package = types.ModuleType("src")
        package.config = config
        spec = importlib.util.spec_from_file_location(
            "snapshot_jwt_under_test", ROOT / "src/aac_app/utils/jwt_utils.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"src": package}):
            spec.loader.exec_module(self.module)

    def test_access_round_trip(self):
        token = self.module.create_access_token({"sub": "synthetic", "user_id": 1})
        self.assertEqual(self.module.decode_access_token(token)["type"], "access")
        self.assertTrue(self.module.validate_token_signature(token))

    def test_refresh_round_trip_only_with_explicit_expected_type(self):
        token = self.module.create_refresh_token({"sub": "synthetic", "user_id": 1})
        self.assertIsNone(self.module.decode_access_token(token))
        self.assertEqual(
            self.module.decode_access_token(token, expected_type="refresh")["type"],
            "refresh",
        )

    def test_access_cannot_refresh(self):
        token = self.module.create_access_token({"sub": "synthetic"})
        self.assertIsNone(self.module.decode_access_token(token, expected_type="refresh"))

    def test_issuer_cannot_override_access_type(self):
        token = self.module.create_access_token({"sub": "synthetic", "type": "refresh"})
        self.assertEqual(self.module.decode_access_token(token)["type"], "access")

    def test_invalid_effective_keys_fail_closed(self):
        token = self.module.create_access_token({"sub": "synthetic"})
        for key in (None, b"x" * 64, "", " " * 64, "x" * 31,
                    "INSECURE_DEFAULT_CHANGE_IN_PRODUCTION",
                    "CHANGE_ME_TO_A_SECURE_RANDOM_STRING"):
            with self.subTest(kind=type(key).__name__, length=len(key) if key is not None else 0):
                self.module.JWT_SECRET_KEY = key
                with self.assertRaises(ValueError):
                    self.module.create_access_token({"sub": "synthetic"})
                with self.assertRaises(ValueError):
                    self.module.create_refresh_token({"sub": "synthetic"})
                self.assertIsNone(self.module.decode_access_token(token))
                self.assertFalse(self.module.validate_token_signature(token))

    def test_expired_access_rejected(self):
        token = self.module.create_access_token({"sub": "synthetic"}, timedelta(seconds=-1))
        self.assertIsNone(self.module.decode_access_token(token))

    def test_wrong_signature_rejected(self):
        token = self.module.create_access_token({"sub": "synthetic"})
        self.module.JWT_SECRET_KEY = secrets.token_hex(32)
        self.assertIsNone(self.module.decode_access_token(token))
        self.assertFalse(self.module.validate_token_signature(token))

    def test_missing_type_and_unknown_expected_type_rejected(self):
        token = self.module.create_access_token({"sub": "synthetic"})
        claims = jwt.decode(token, self.key, algorithms=["HS256"])
        del claims["type"]
        legacy = jwt.encode(claims, self.key, algorithm="HS256")
        self.assertIsNone(self.module.decode_access_token(legacy))
        self.assertIsNone(self.module.decode_access_token(token, expected_type="unknown"))

    def test_wrong_issuer_rejected(self):
        token = self.module.create_access_token({"sub": "synthetic"})
        claims = jwt.decode(token, self.key, algorithms=["HS256"])
        claims["iss"] = "other"
        self.assertIsNone(self.module.decode_access_token(jwt.encode(claims, self.key, algorithm="HS256")))

    def test_refresh_route_explicitly_selects_refresh_type(self):
        tree = ast.parse((ROOT / "src/api/routers/auth.py").read_text())
        endpoint = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "refresh_access_token")
        calls = [node for node in ast.walk(endpoint) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "decode_access_token"]
        self.assertEqual(len(calls), 1)
        self.assertTrue(any(arg.arg == "expected_type" and isinstance(arg.value, ast.Constant)
                            and arg.value.value == "refresh" for arg in calls[0].keywords))


if __name__ == "__main__":
    unittest.main()
