#!/usr/bin/env python3
"""Check docstring coverage and section quality for project Python files.

This checker is intentionally lightweight so it can run in pre-commit. It reports
missing module/class/callable docstrings and required section headers for public
callables in core modules.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable


@dataclass(slots=True)
class Finding:
    """One documentation-quality issue emitted by the checker."""

    path: Path
    line: int
    symbol: str
    message: str


def _iter_python_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files


def _has_non_none_return(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for nested in ast.walk(node):
        if not isinstance(nested, ast.Return) or nested.value is None:
            continue
        if isinstance(nested.value, ast.Constant) and nested.value.value is None:
            continue
        return True
    return False


def _has_explicit_raise(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(nested, ast.Raise) for nested in ast.walk(node))


def _has_nontrivial_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    positional = [arg.arg for arg in node.args.args if arg.arg not in {"self", "cls"}]
    keyword_only = [arg.arg for arg in node.args.kwonlyargs]
    return bool(positional or keyword_only or node.args.vararg or node.args.kwarg)


def _missing_sections(
    docstring: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    missing: list[str] = []
    if _has_nontrivial_params(node) and "Args:" not in docstring:
        missing.append("Args")
    if _has_non_none_return(node) and "Returns:" not in docstring:
        missing.append("Returns")
    if _has_explicit_raise(node) and "Raises:" not in docstring:
        missing.append("Raises")
    return missing


def _is_tests_path(path: Path) -> bool:
    return "tests" in path.parts


def _check_module(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))

    module_doc = ast.get_docstring(module)
    if module_doc is None:
        findings.append(
            Finding(
                path=path,
                line=1,
                symbol="<module>",
                message="Missing module docstring.",
            )
        )

    in_tests = _is_tests_path(path)
    for node in module.body:
        if isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node)
            if class_doc is None:
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        symbol=node.name,
                        message="Missing class docstring.",
                    )
                )

            if in_tests or node.name.startswith("_"):
                continue

            for member in node.body:
                if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if member.name.startswith("_"):
                    continue
                method_doc = ast.get_docstring(member)
                if method_doc is None:
                    findings.append(
                        Finding(
                            path=path,
                            line=member.lineno,
                            symbol=f"{node.name}.{member.name}",
                            message="Missing public method docstring.",
                        )
                    )
                    continue
                missing = _missing_sections(method_doc, member)
                if missing:
                    findings.append(
                        Finding(
                            path=path,
                            line=member.lineno,
                            symbol=f"{node.name}.{member.name}",
                            message=(
                                "Missing docstring section(s): "
                                + ", ".join(missing)
                                + "."
                            ),
                        )
                    )

        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        if in_tests and node.name.startswith("test_"):
            continue

        fn_doc = ast.get_docstring(node)
        if fn_doc is None:
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    symbol=node.name,
                    message="Missing function docstring.",
                )
            )
            continue

        if in_tests:
            continue

        missing = _missing_sections(fn_doc, node)
        if missing:
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    symbol=node.name,
                    message="Missing docstring section(s): " + ", ".join(missing) + ".",
                )
            )

    return findings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("docugym"), Path("tests")],
        help="Files or directories to inspect.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when findings are present.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the documentation checker CLI and print findings."""

    args = _parse_args()
    files = _iter_python_files(args.paths)
    findings: list[Finding] = []
    for file_path in files:
        findings.extend(_check_module(file_path))

    if not findings:
        print("doc-quality: no issues found")
        return 0

    for issue in findings:
        print(f"{issue.path}:{issue.line}: {issue.symbol}: {issue.message}")

    print(f"doc-quality: {len(findings)} issue(s) found")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
