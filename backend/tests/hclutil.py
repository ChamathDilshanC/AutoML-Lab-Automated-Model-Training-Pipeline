"""Reading the repository's Terraform from tests, without a Terraform binary."""

from pathlib import Path
from typing import Any

import hcl2

INFRA = Path(__file__).resolve().parents[2] / "infrastructure" / "terraform"
_NOISE = {"__is_block__", "__comments__"}


def _unquote(text: str) -> str:
    return text[1:-1] if len(text) >= 2 and text[0] == '"' and text[-1] == '"' else text


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {_unquote(k): _clean(v) for k, v in value.items() if k not in _NOISE}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, str):
        return _unquote(value)
    return value


def load(name: str) -> dict[str, Any]:
    """Parse one .tf file into plain dicts, with quotes and parser bookkeeping removed."""
    return dict(_clean(hcl2.loads((INFRA / name).read_text(encoding="utf-8"))))


def blocks(document: dict[str, Any], section: str, kind: str) -> dict[str, Any]:
    """Every `section "kind" "label" {...}` block, by label. `section` is resource or data."""
    found: dict[str, Any] = {}
    for entry in document.get(section, []):
        found.update(entry.get(kind, {}))
    return found


def variables(document: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for entry in document.get("variable", []):
        found.update(entry)
    return found


def one(body: Any) -> Any:
    """The parser wraps every nested block in a list."""
    return body[0] if isinstance(body, list) else body


def policy_actions(label: str) -> set[str]:
    """All IAM actions granted by the `aws_iam_policy_document` data block named `label`."""
    body = blocks(load("iam.tf"), "data", "aws_iam_policy_document")[label]
    return {action for statement in body["statement"] for action in statement["actions"]}
