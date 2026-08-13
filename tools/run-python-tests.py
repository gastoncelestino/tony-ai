#!/usr/bin/env python3
"""
Standalone Python test runner for Tony-AI.

Purpose
-------
Provide a stdlib-only fallback when pytest is unavailable.

The runner intentionally supports only test semantics that can be reproduced
reliably with the Python standard library:

- unittest.TestCase classes
- module-level test_* functions with no required arguments

It does NOT try to emulate pytest fixtures, parametrization, plugins, or other
pytest-specific behavior. If such a construct is detected, the runner fails
explicitly instead of silently skipping it.

Usage
-----
    python3 tools/run-python-tests.py tests
    python3 tools/run-python-tests.py tests/test_kernel_cli.py
    python3 tools/run-python-tests.py tests/test_kernel_*.py

Exit codes
----------
0 = all discovered tests passed
1 = test failure, test error, import error, unsupported test semantics,
    or zero tests discovered
2 = invalid command-line usage
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import sys
import traceback
import types
import unittest
from pathlib import Path
from typing import Iterable


TEST_FILE_PATTERN = "test_*.py"


class RunnerError(RuntimeError):
    """Raised for configuration or discovery errors."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Python tests without pytest.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Test files or directories containing test_*.py files.",
    )
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
            for candidate in path.rglob(TEST_FILE_PATTERN):
                if candidate.is_file() and candidate.name != "__init__.py":
                    discovered.add(candidate.resolve())
            continue

        if path.is_file():
            if path.name.startswith("test_") and path.suffix == ".py":
                discovered.add(path)
            else:
                raise RunnerError(
                    f"file does not match {TEST_FILE_PATTERN}: {path}"
                )
            continue

        raise RunnerError(f"unsupported path: {path}")

    return sorted(discovered)


def module_name_for(path: Path, index: int) -> str:
    """
    Generate a deterministic, collision-resistant module name.

    The generated name is intentionally not the normal package name because
    multiple paths can point at files with the same basename.
    """
    safe_stem = "".join(
        char if char.isalnum() or char == "_" else "_"
        for char in path.stem
    )
    return f"_tony_ai_fallback_test_{index}_{safe_stem}"


def import_test_module(path: Path, index: int) -> types.ModuleType:
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
        raise RunnerError(
            f"failed to import {path}: {type(exc).__name__}: {exc}"
        ) from exc

    return module


def required_parameters(function: object) -> list[str]:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return []

    required: list[str] = []

    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)

    return required


def detect_unsupported_function(function: object, module: types.ModuleType) -> None:
    """
    Reject function signatures that require pytest fixture injection.

    A zero-argument test function can be executed faithfully by this runner.
    A required argument means the caller is expected to inject something,
    which is normally pytest fixture behavior in this project.
    """
    required = required_parameters(function)

    if required:
        name = getattr(function, "__name__", repr(function))
        raise RunnerError(
            f"{module.__file__}: test function {name} requires "
            f"arguments {required}; pytest-specific fixture injection is "
            "not supported by the standalone runner"
        )


def add_unittest_cases(
    suite: unittest.TestSuite,
    module: types.ModuleType,
    loader: unittest.TestLoader,
) -> int:
    count = 0

    for name, obj in inspect.getmembers(module, inspect.isclass):
        if not issubclass(obj, unittest.TestCase):
            continue

        # Only collect classes actually defined in this module.
        # This prevents imported TestCase classes from being executed twice.
        if obj.__module__ != module.__name__:
            continue

        tests = loader.loadTestsFromTestCase(obj)
        suite.addTests(tests)
        count += tests.countTestCases()

    return count


def add_function_tests(
    suite: unittest.TestSuite,
    module: types.ModuleType,
) -> int:
    count = 0

    for name, function in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("test_"):
            continue

        # Only collect functions actually defined in this module.
        if function.__module__ != module.__name__:
            continue

        detect_unsupported_function(function, module)

        case = unittest.FunctionTestCase(
            function,
            description=f"{module.__file__}:{name}",
        )
        suite.addTest(case)
        count += 1

    return count


def build_suite(
    test_files: list[Path],
) -> tuple[unittest.TestSuite, int]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    total = 0

    for index, path in enumerate(test_files):
        print(f"▶ Discovering {path}")

        module = import_test_module(path, index)

        module_suite = unittest.TestSuite()

        class_count = add_unittest_cases(
            module_suite,
            module,
            loader,
        )

        function_count = add_function_tests(
            module_suite,
            module,
        )

        module_count = class_count + function_count

        if module_count == 0:
            raise RunnerError(
                f"{path}: no tests discovered; refusing to report success"
            )

        suite.addTests(module_suite)
        total += module_count

        print(
            f"  ✓ discovered {module_count} test(s) "
            f"({class_count} unittest, {function_count} function)"
        )

    return suite, total


def run_suite(
    suite: unittest.TestSuite,
    total: int,
) -> int:
    print()
    print(f"▶ Running {total} Python test(s) with stdlib unittest...")
    print()

    runner = unittest.TextTestRunner(
        verbosity=2,
        failfast=False,
    )

    result = runner.run(suite)

    print()
    print(
        "Summary: "
        f"tests={result.testsRun} "
        f"failures={len(result.failures)} "
        f"errors={len(result.errors)} "
        f"skipped={len(result.skipped)}"
    )

    if result.testsRun != total:
        print(
            "ERROR: discovered test count does not match executed test count "
            f"({total} discovered, {result.testsRun} executed)."
        )
        return 1

    if not result.wasSuccessful():
        return 1

    print("✓ Standalone Python test suite passed")
    return 0


def main() -> int:
    args = parse_args()

    # Ensure project imports such as `from kernel...` work exactly as they do
    # when the project is executed from its root directory.
    root = repo_root()

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        test_files = resolve_test_files(args.paths)

        if not test_files:
            raise RunnerError(
                "no test files discovered; refusing to report success"
            )

        print(f"Found {len(test_files)} test file(s).")

        suite, total = build_suite(test_files)

        if total == 0:
            raise RunnerError(
                "zero tests discovered; refusing to report success"
            )

        return run_suite(suite, total)

    except RunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(
            f"ERROR: unexpected runner failure: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())