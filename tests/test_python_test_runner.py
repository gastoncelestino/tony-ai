"""Tests for tests/python_verify.py.

These tests intentionally use only the Python standard library so they can
validate the fallback runner even when pytest is unavailable.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tools" / "python_verify.py"


class PythonTestRunnerTests(unittest.TestCase):
    def run_runner(self, *paths: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), *(str(path) for path in paths)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_test_file(self, directory: Path, name: str, source: str) -> Path:
        path = directory / name
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    def test_discovers_module_functions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = self.write_test_file(Path(tmp), "test_functions.py", """
                def test_first():
                    assert 1 + 1 == 2

                def test_second():
                    assert "tony".upper() == "TONY"
            """)
            result = self.run_runner(test_file)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("discovered 2 test(s)", result.stdout)
            self.assertIn("tests=2", result.stdout)
            self.assertIn("failures=0", result.stdout)

    def test_discovers_unittest_testcase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = self.write_test_file(Path(tmp), "test_unittest.py", """
                import unittest

                class ExampleTests(unittest.TestCase):
                    def test_one(self):
                        self.assertEqual(2 + 2, 4)

                    def test_two(self):
                        self.assertTrue(True)
            """)
            result = self.run_runner(test_file)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("tests=2", result.stdout)

    def test_does_not_silently_skip_required_function_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = self.write_test_file(Path(tmp), "test_fixture_like.py", """
                def test_requires_fixture(client):
                    assert client is not None
            """)
            result = self.run_runner(test_file)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pytest-specific fixture injection is not supported", result.stderr)

    def test_rejects_pytest_specific_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = self.write_test_file(Path(tmp), "test_pytest_only.py", """
                import pytest

                @pytest.mark.parametrize("value", [1, 2])
                def test_values(value):
                    assert value > 0
            """)
            result = self.run_runner(test_file)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pytest-specific semantics detected", result.stderr)

    def test_rejects_async_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = self.write_test_file(Path(tmp), "test_async.py", """
                async def test_async():
                    return None
            """)
            result = self.run_runner(test_file)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("async test function", result.stderr)

    def test_propagates_test_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = self.write_test_file(Path(tmp), "test_failure.py", """
                def test_failure():
                    assert False, "intentional failure"
            """)
            result = self.run_runner(test_file)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("failures=1", result.stdout)

    def test_rejects_zero_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = self.write_test_file(Path(tmp), "test_empty.py", """
                VALUE = 42
            """)
            result = self.run_runner(test_file)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no tests discovered", result.stderr)

    def test_discovers_all_test_files_in_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.write_test_file(directory, "test_one.py", """
                def test_one():
                    assert True
            """)
            self.write_test_file(directory, "test_two.py", """
                def test_two():
                    assert True
            """)
            result = self.run_runner(directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Found 2 test file(s)", result.stdout)
            self.assertIn("tests=2", result.stdout)


if __name__ == "__main__":
    unittest.main()
