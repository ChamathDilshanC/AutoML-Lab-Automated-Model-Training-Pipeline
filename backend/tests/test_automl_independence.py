"""The ML engine must stay free of web and cloud dependencies (ADR 0001)."""

import ast
from pathlib import Path

FORBIDDEN = {"fastapi", "starlette", "uvicorn", "boto3", "botocore", "app"}
AUTOML_DIR = Path(__file__).resolve().parent.parent / "automl"


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_automl_does_not_import_web_or_cloud_packages() -> None:
    offenders = {
        str(path.relative_to(AUTOML_DIR)): sorted(_imported_roots(path) & FORBIDDEN)
        for path in AUTOML_DIR.rglob("*.py")
        if _imported_roots(path) & FORBIDDEN
    }
    assert not offenders, f"Forbidden imports in automl: {offenders}"
