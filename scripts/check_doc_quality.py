#!/usr/bin/env python3
"""Check docstring coverage, section quality, and documentation depth.

The checker validates presence, required Google-style sections, and a coarse
documentation level for modules, classes, and public callables.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
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


@dataclass(slots=True)
class AuditRecord:
    """One symbol-level documentation audit record."""

    path: Path
    line: int
    symbol: str
    kind: str
    scope: str
    level: str


LEVEL_ORDER = ("bare", "minimal", "standard", "rich")
LEVEL_RANK = {name: index for index, name in enumerate(LEVEL_ORDER)}
SECTION_HEADERS = (
    "Args:",
    "Returns:",
    "Raises:",
    "Notes:",
    "Example:",
    "Examples:",
)


def _count_words(text: str) -> int:
    """Count whitespace-delimited tokens for depth heuristics.

    The checker uses a simple token count because it is deterministic, cheap, and
    stable in pre-commit runs. The count feeds level classification thresholds.

    Args:
        text: Docstring text to evaluate.

    Returns:
        Approximate word/token count.
    """

    return sum(1 for token in text.replace("\n", " ").split() if token.strip())


def _doc_level_module(docstring: str | None) -> str:
    """Classify module-doc depth for reporting and threshold checks.

    Modules without docstrings are ``bare``. Short summaries become ``minimal``.
    Longer docs with context-oriented sections are classified as ``rich``;
    otherwise they are ``standard``.

    Args:
        docstring: Module docstring text, if present.

    Returns:
        One of ``bare``, ``minimal``, ``standard``, or ``rich``.
    """

    if docstring is None:
        return "bare"

    words = _count_words(docstring)
    if words < 8:
        return "minimal"
    if words >= 28 and any(
        header in docstring for header in ("Notes:", "Example:", "Examples:")
    ):
        return "rich"
    return "standard"


def _doc_level_class(docstring: str | None) -> str:
    """Classify class-doc depth for reporting and threshold checks.

    Rich class docs should include role/lifecycle detail or explicit sections
    (for example ``Attributes`` or ``Notes``), while one-liners remain minimal.

    Args:
        docstring: Class docstring text, if present.

    Returns:
        One of ``bare``, ``minimal``, ``standard``, or ``rich``.
    """

    if docstring is None:
        return "bare"

    words = _count_words(docstring)
    if words < 6:
        return "minimal"
    if words >= 24 and any(
        header in docstring
        for header in ("Attributes:", "Notes:", "Example:", "Examples:")
    ):
        return "rich"
    return "standard"


def _doc_level_callable(
    docstring: str | None,
    missing_sections: list[str],
) -> str:
    """Classify callable-doc depth using section completeness and length.

    This classifier intentionally treats section omissions as ``minimal`` even when
    a docstring exists, because callable contracts are where ambiguous behavior can
    most easily cause user or maintainer errors.

    Args:
        docstring: Function/method docstring text, if present.
        missing_sections: Required section headers absent from ``docstring``.

    Returns:
        One of ``bare``, ``minimal``, ``standard``, or ``rich``.
    """

    if docstring is None:
        return "bare"

    words = _count_words(docstring)
    if missing_sections or words < 6:
        return "minimal"

    if words >= 30 and any(
        header in docstring for header in ("Notes:", "Example:", "Examples:")
    ):
        return "rich"

    return "standard"


def _iter_python_files(paths: Iterable[Path]) -> list[Path]:
    """Expand path arguments into a deterministic list of Python files.

    Deterministic ordering keeps checker output stable across runs, which makes
    pre-commit and CI diagnostics easier to diff and review.

    Args:
        paths: File and directory paths supplied by CLI arguments.

    Returns:
        Sorted list of Python files to audit.
    """

    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files


def _has_non_none_return(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Detect whether a callable has any explicit non-``None`` return.

    The result determines whether ``Returns`` documentation should be required.

    Args:
        node: Function/method AST node to inspect.

    Returns:
        ``True`` if the callable returns a meaningful value in at least one path.
    """

    for nested in ast.walk(node):
        if not isinstance(nested, ast.Return) or nested.value is None:
            continue
        if isinstance(nested.value, ast.Constant) and nested.value.value is None:
            continue
        return True
    return False


def _has_explicit_raise(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Detect whether a callable explicitly raises an exception.

    This is used to decide whether ``Raises`` should be treated as a required
    docstring section.

    Args:
        node: Function/method AST node to inspect.

    Returns:
        ``True`` if any ``raise`` statement exists in the callable body.
    """

    return any(isinstance(nested, ast.Raise) for nested in ast.walk(node))


def _has_nontrivial_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Detect whether a callable signature warrants ``Args`` documentation.

    ``self``/``cls`` are ignored so methods with no real inputs do not get
    penalized for omitting an ``Args`` section.

    Args:
        node: Function/method AST node to inspect.

    Returns:
        ``True`` when the callable has meaningful positional/keyword parameters.
    """

    positional = [arg.arg for arg in node.args.args if arg.arg not in {"self", "cls"}]
    keyword_only = [arg.arg for arg in node.args.kwonlyargs]
    return bool(positional or keyword_only or node.args.vararg or node.args.kwarg)


def _missing_sections(
    docstring: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    """Compute missing required section headers for one callable docstring.

    Section requirements are inferred from signature and body semantics so the
    checker enforces useful documentation, not boilerplate for trivial callables.

    Args:
        docstring: Callable docstring text.
        node: Callable AST node used to infer required sections.

    Returns:
        Ordered list of missing section names.
    """

    missing: list[str] = []
    if _has_nontrivial_params(node) and "Args:" not in docstring:
        missing.append("Args")
    if _has_non_none_return(node) and "Returns:" not in docstring:
        missing.append("Returns")
    if _has_explicit_raise(node) and "Raises:" not in docstring:
        missing.append("Raises")
    return missing


def _is_tests_path(path: Path) -> bool:
    """Classify whether a path belongs to test scope.

    Test scope uses a different minimum level threshold so concise helper docs do
    not block merges while still preventing undocumented test scaffolding.

    Args:
        path: File path currently being audited.

    Returns:
        ``True`` when the path is under a ``tests`` directory.
    """

    return "tests" in path.parts


def _check_module(path: Path) -> tuple[list[Finding], list[AuditRecord]]:
    """Audit one Python module for coverage, section quality, and depth.

    This function is the core analyzer. It emits user-facing ``Finding`` records
    for policy violations and ``AuditRecord`` rows for level summaries and
    threshold checks.

    Args:
        path: Python source file to parse and audit.

    Returns:
        Tuple ``(findings, records)`` where findings are violations and records are
        complete symbol-level audit entries.
    """

    findings: list[Finding] = []
    records: list[AuditRecord] = []
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))

    module_doc = ast.get_docstring(module)
    scope = "tests" if _is_tests_path(path) else "core"
    records.append(
        AuditRecord(
            path=path,
            line=1,
            symbol="<module>",
            kind="module",
            scope=scope,
            level=_doc_level_module(module_doc),
        )
    )

    if module_doc is None:
        findings.append(
            Finding(
                path=path,
                line=1,
                symbol="<module>",
                message="Missing module docstring.",
            )
        )

    in_tests = scope == "tests"
    for node in module.body:
        if isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node)
            records.append(
                AuditRecord(
                    path=path,
                    line=node.lineno,
                    symbol=node.name,
                    kind="class",
                    scope=scope,
                    level=_doc_level_class(class_doc),
                )
            )

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
                missing = []
                if method_doc is not None:
                    missing = _missing_sections(method_doc, member)

                records.append(
                    AuditRecord(
                        path=path,
                        line=member.lineno,
                        symbol=f"{node.name}.{member.name}",
                        kind="method",
                        scope=scope,
                        level=_doc_level_callable(method_doc, missing),
                    )
                )

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
        missing = []
        if fn_doc is not None:
            missing = _missing_sections(fn_doc, node)

        records.append(
            AuditRecord(
                path=path,
                line=node.lineno,
                symbol=node.name,
                kind="function",
                scope=scope,
                level=_doc_level_callable(fn_doc, missing),
            )
        )

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

        if missing:
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    symbol=node.name,
                    message="Missing docstring section(s): " + ", ".join(missing) + ".",
                )
            )

    return findings, records


def _required_level(scope: str, args: argparse.Namespace) -> str:
    """Return the configured minimum documentation level for one scope.

    Args:
        scope: Audit scope label (``core`` or ``tests``).
        args: Parsed CLI arguments containing threshold settings.

    Returns:
        Required minimum level for the provided scope.
    """

    return args.min_level_tests if scope == "tests" else args.min_level_core


def _enforce_level_thresholds(
    records: list[AuditRecord],
    args: argparse.Namespace,
) -> list[Finding]:
    """Convert depth-threshold misses into standard checker findings.

    Keeping level-threshold failures in the same ``Finding`` format ensures strict
    mode and CI output remain consistent with section/coverage violations.

    Args:
        records: Symbol-level audit records produced by module analysis.
        args: Parsed CLI arguments with scope threshold configuration.

    Returns:
        Findings for symbols that do not meet configured depth thresholds.
    """

    findings: list[Finding] = []
    for record in records:
        required = _required_level(record.scope, args)
        if LEVEL_RANK[record.level] >= LEVEL_RANK[required]:
            continue
        findings.append(
            Finding(
                path=record.path,
                line=record.line,
                symbol=record.symbol,
                message=(
                    f"Documentation level '{record.level}' below required "
                    f"'{required}' for {record.scope} {record.kind}."
                ),
            )
        )
    return findings


def _print_level_summary(records: list[AuditRecord]) -> None:
    """Print aggregate documentation-level statistics by scope.

    The summary is primarily a governance signal: teams can tighten thresholds
    based on distribution trends without parsing raw findings manually.

    Args:
        records: Symbol-level audit records to aggregate.
    """

    if not records:
        print("doc-quality levels: no symbols inspected")
        return

    by_scope: dict[str, Counter[str]] = {
        "core": Counter(),
        "tests": Counter(),
    }
    for record in records:
        by_scope[record.scope][record.level] += 1

    total_counts = Counter(record.level for record in records)
    total_text = " ".join(f"{level}={total_counts[level]}" for level in LEVEL_ORDER)
    print(f"doc-quality levels total: symbols={len(records)} {total_text}")

    for scope in ("core", "tests"):
        scope_counts = by_scope[scope]
        scope_text = " ".join(f"{level}={scope_counts[level]}" for level in LEVEL_ORDER)
        print(
            f"doc-quality levels {scope}: symbols={sum(scope_counts.values())} "
            f"{scope_text}"
        )


def _parse_args() -> argparse.Namespace:
    """Define and parse CLI arguments for doc-quality enforcement.

    The parser exposes strict mode and scope-level threshold controls so the same
    script can serve local iteration, pre-commit enforcement, and CI hard gates.

    Returns:
        Parsed CLI argument namespace.
    """

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
    parser.add_argument(
        "--min-level-core",
        choices=LEVEL_ORDER,
        default="standard",
        help="Minimum documentation level for non-test symbols.",
    )
    parser.add_argument(
        "--min-level-tests",
        choices=LEVEL_ORDER,
        default="minimal",
        help="Minimum documentation level for test symbols.",
    )
    parser.add_argument(
        "--no-level-summary",
        action="store_true",
        help="Suppress level-summary output.",
    )
    return parser.parse_args()


def main() -> int:
    """Run end-to-end documentation-quality analysis.

    The pipeline expands targets, audits symbols, enforces level thresholds,
    optionally prints level summaries, and returns a process code compatible with
    pre-commit and CI policy gates.

    Returns:
        Process exit code (``0`` for pass, ``1`` for strict-mode violations).
    """

    args = _parse_args()
    files = _iter_python_files(args.paths)
    findings: list[Finding] = []
    records: list[AuditRecord] = []
    for file_path in files:
        module_findings, module_records = _check_module(file_path)
        findings.extend(module_findings)
        records.extend(module_records)

    findings.extend(_enforce_level_thresholds(records, args))

    if not args.no_level_summary:
        _print_level_summary(records)

    if not findings:
        print("doc-quality: no issues found")
        return 0

    for issue in findings:
        print(f"{issue.path}:{issue.line}: {issue.symbol}: {issue.message}")

    print(f"doc-quality: {len(findings)} issue(s) found")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
