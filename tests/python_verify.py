#!/usr/bin/env python3
"""Standalone Python test runner for Tony-AI.

Uses only the Python standard library. Supports unittest.TestCase classes and
module-level test_* functions without required arguments. It deliberately
rejects pytest-specific semantics instead of trying to emulate pytest.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import inspect
import os
import sys
import traceback
import types
import unittest
from pathlib import Path
from typing import Iterable

TEST_FILE_PATTERN = "test_*.py"


def _load_project_env() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = os.path.expandvars(value.strip())
        if key and value:
            os.environ.setdefault(key, value)


_load_project_env()
_CACHE_ROOT = Path(os.path.expanduser(os.environ.get("PYTHON_CACHE_DIR", "~/.tony-ai/pycache")))
_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PYTHON_CACHE_DIR", str(_CACHE_ROOT))
os.environ.setdefault("TONY_RUNTIME_DIR", str(_CACHE_ROOT.parent))
os.environ["PYTHONPYCACHEPREFIX"] = str(_CACHE_ROOT)
if hasattr(sys, "pycache_prefix"):
    sys.pycache_prefix = str(_CACHE_ROOT)
sys.dont_write_bytecode = True


class RunnerError(RuntimeError):
    """Raised for configuration or discovery errors."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Python tests without pytest.")
    parser.add_argument("paths", nargs="+", help="Test files or directories containing test_*.py files.")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_test_files(paths: Iterable[str]) -> list[Path]:
    root = repo_root()
    discovered: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if not path.exists():
            raise RunnerError(f"path does not exist: {path}")
        if path.is_dir():
            discovered.update(candidate.resolve() for candidate in path.rglob(TEST_FILE_PATTERN) if candidate.is_file())
        elif path.is_file():
            if path.name.startswith("test_") and path.suffix == ".py":
                discovered.add(path)
            else:
                raise RunnerError(f"file does not match {TEST_FILE_PATTERN}: {path}")
        else:
            raise RunnerError(f"unsupported path: {path}")
    return sorted(discovered)


def module_name_for(path: Path, index: int) -> str:
    root = repo_root()
    try:
        rel = path.relative_to(root)
        return ".".join(rel.with_suffix("").parts)
    except ValueError:
        parent_str = str(path.parent)
        if parent_str not in sys.path:
            sys.path.insert(0, parent_str)
        return path.stem



def detect_unsupported_source(path: Path) -> None:
    """Reject pytest-only constructs before importing the test module."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise RunnerError(f"cannot inspect {path}: {type(exc).__name__}: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef,)) and node.name.startswith("test_"):
            raise RunnerError(f"{path}: async test function {node.name} is not supported by the standalone runner")
        if isinstance(node, ast.Import):
            if any(alias.name == "pytest" for alias in node.names):
                raise RunnerError(f"{path}: pytest-specific semantics detected (import pytest); standalone runner cannot execute this test")
        elif isinstance(node, ast.ImportFrom) and node.module and (node.module == "pytest" or node.module.startswith("pytest.")):
            raise RunnerError(f"{path}: pytest-specific semantics detected (pytest import); standalone runner cannot execute this test")
        elif isinstance(node, ast.Name) and node.id == "pytest":
            raise RunnerError(f"{path}: pytest-specific semantics detected; standalone runner cannot execute this test")


def import_test_module(path: Path, index: int) -> types.ModuleType:
    detect_unsupported_source(path)
    module_name = module_name_for(path, index)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RunnerError(f"cannot create import spec for: {path}")
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise RunnerError(f"failed to import {path}: {type(exc).__name__}: {exc}") from exc
    return module


def required_parameters(function: object) -> list[str]:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return []
    return [
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and parameter.default is inspect.Parameter.empty
    ]


def detect_unsupported_function(function: object, module: types.ModuleType) -> None:
    name = getattr(function, "__name__", repr(function))
    if inspect.iscoroutinefunction(function):
        raise RunnerError(f"{module.__file__}: async test function {name} is not supported by the standalone runner")
    required = required_parameters(function)
    if required:
        raise RunnerError(
            f"{module.__file__}: test function {name} requires arguments {required}; "
            "pytest-specific fixture injection is not supported by the standalone runner"
        )


def add_unittest_cases(suite: unittest.TestSuite, module: types.ModuleType, loader: unittest.TestLoader) -> int:
    count = 0
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if not issubclass(obj, unittest.TestCase) or obj.__module__ != module.__name__:
            continue
        tests = loader.loadTestsFromTestCase(obj)
        suite.addTests(tests)
        count += tests.countTestCases()
    return count


def add_function_tests(suite: unittest.TestSuite, module: types.ModuleType) -> int:
    count = 0
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("test_") or function.__module__ != module.__name__:
            continue
        detect_unsupported_function(function, module)
        suite.addTest(unittest.FunctionTestCase(function, description=f"{module.__file__}:{name}"))
        count += 1
    return count


def build_suite(test_files: list[Path]) -> tuple[unittest.TestSuite, int]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    total = 0
    for index, path in enumerate(test_files):
        print(f"▶ Discovering {path}")
        module = import_test_module(path, index)
        module_suite = unittest.TestSuite()
        class_count = add_unittest_cases(module_suite, module, loader)
        function_count = add_function_tests(module_suite, module)
        module_count = class_count + function_count
        if module_count == 0:
            raise RunnerError(f"{path}: no tests discovered; refusing to report success")
        suite.addTests(module_suite)
        total += module_count
        print(f"  ✓ discovered {module_count} test(s) ({class_count} unittest, {function_count} function)")
    return suite, total


def run_suite(suite: unittest.TestSuite, total: int) -> int:
    print()
    print(f"▶ Running {total} Python test(s) with stdlib unittest...")
    print()
    result = unittest.TextTestRunner(verbosity=2, failfast=False).run(suite)
    print()
    print(f"Summary: tests={result.testsRun} failures={len(result.failures)} errors={len(result.errors)} skipped={len(result.skipped)}")
    if result.testsRun != total:
        print(f"ERROR: discovered test count does not match executed test count ({total} discovered, {result.testsRun} executed).")
        return 1
    if not result.wasSuccessful():
        return 1
    print("✓ Standalone Python test suite passed")
    return 0


def main() -> int:
    args = parse_args()
    root = repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        test_files = resolve_test_files(args.paths)
        if not test_files:
            raise RunnerError("no test files discovered; refusing to report success")
        print(f"Found {len(test_files)} test file(s).")
        suite, total = build_suite(test_files)
        if total == 0:
            raise RunnerError("zero tests discovered; refusing to report success")
        return run_suite(suite, total)
    except RunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: unexpected runner failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
