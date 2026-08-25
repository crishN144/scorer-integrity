"""Structural test: no module may reach the model provider directly.

This is the test that would have prevented the $1.50-ceiling overrun. The ceiling
was declared in a YAML config and the script that spent the money never read it,
because the guard lived in a *different* script and opting in was voluntary.

A guard nobody is forced to use is not a guard. This test makes bypassing it a
build failure rather than an oversight.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "scorer_integrity"

# budget.py is the guarded path itself, so it is the one place allowed to call
# the provider. Nothing else may.
ALLOWED = {"budget.py"}


def _python_files() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _direct_provider_calls(path: Path) -> list[int]:
    """Return line numbers where `get_model(...)` is called directly.

    Calls whose first argument is a free model (mockllm) are permitted, since
    they cannot cost anything.

    Args:
        path: File to scan.

    Returns:
        Offending line numbers.
    """
    tree = ast.parse(path.read_text())
    offending: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "get_model":
            continue
        first = node.args[0] if node.args else None
        if (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and first.value.startswith("mockllm")
        ):
            continue
        offending.append(node.lineno)
    return offending


@pytest.mark.parametrize(
    "path", _python_files(), ids=[str(p.relative_to(PACKAGE)) for p in _python_files()]
)
def test_no_module_bypasses_the_budget_guard(path: Path) -> None:
    """Only `budget.py` may call the provider directly.

    Args:
        path: The module under test.
    """
    if path.name in ALLOWED:
        return
    offending = _direct_provider_calls(path)
    assert not offending, (
        f"{path.relative_to(PACKAGE)} calls get_model directly at line(s) {offending}. "
        f"Use scorer_integrity.budget.budgeted_model so the cost ceiling is enforced."
    )


def test_the_guard_itself_exists_and_is_the_only_exception() -> None:
    """Guard against the exception list quietly growing."""
    assert {"budget.py"} == ALLOWED
    assert (PACKAGE / "budget.py").exists()
