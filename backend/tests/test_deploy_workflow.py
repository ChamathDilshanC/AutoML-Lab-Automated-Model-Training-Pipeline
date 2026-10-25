"""Static checks of .github/workflows/deploy.yml: no long-lived AWS keys, gated, least privilege."""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    loaded["on"] = loaded.pop(True)  # YAML reads the key `on` as the boolean True
    return dict(loaded)


@pytest.fixture(scope="module")
def steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return list(workflow["jobs"]["deploy"]["steps"])


def test_it_runs_on_main_and_by_hand_only(workflow: dict[str, Any]) -> None:
    assert workflow["on"] == {"push": {"branches": ["main"]}, "workflow_dispatch": None}


def test_the_token_can_only_read_the_repository_and_mint_an_oidc_token(
    workflow: dict[str, Any],
) -> None:
    assert workflow["permissions"] == {"contents": "read", "id-token": "write"}


def test_nothing_deploys_until_it_is_switched_on_and_approved(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["deploy"]
    assert job["if"] == "vars.DEPLOY_ENABLED == 'true'"
    assert job["environment"] == "production"  # matches the OIDC trust condition in cicd.tf
    assert workflow["concurrency"]["cancel-in-progress"] is False  # never half-cancel a deploy


def test_aws_is_reached_through_oidc_with_no_stored_keys(steps: list[dict[str, Any]]) -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text
    for forbidden in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "aws-access-key-id"):
        assert forbidden not in text
    login = next(
        s for s in steps if s.get("uses", "").startswith("aws-actions/configure-aws-credentials")
    )
    assert login["with"]["role-to-assume"] == "${{ vars.AWS_DEPLOY_ROLE_ARN }}"


def test_the_environment_matches_the_trust_policy() -> None:
    from tests.hclutil import load, variables

    default = variables(load("variables.tf"))["github_environment"]["default"]
    assert default == "production"


def test_it_builds_pushes_both_tags_then_deploys_api_and_worker(
    steps: list[dict[str, Any]],
) -> None:
    runs = "\n".join(s.get("run", "") for s in steps)
    assert '"$REGISTRY/$ECR_REPOSITORY:$GITHUB_SHA"' in runs
    assert '"$REGISTRY/$ECR_REPOSITORY:latest"' in runs
    assert runs.index("docker build") < runs.index("docker push")
    assert runs.index("docker push") < runs.index("aws lambda update-function-code")
    assert runs.index("aws lambda update-function-code") < runs.index("aws ecs update-service")
    assert "--force-new-deployment" in runs
    assert "/health" in runs  # a smoke test closes the job
    assert "apprunner" not in runs


def test_the_api_is_deployed_as_a_single_manifest_image_by_commit(
    steps: list[dict[str, Any]],
) -> None:
    runs = "\n".join(s.get("run", "") for s in steps)
    assert "--provenance=false" in runs  # Lambda rejects a multi-manifest index
    assert '--image-uri "$REGISTRY/$ECR_REPOSITORY:$GITHUB_SHA"' in runs


def test_the_functions_secrets_never_reach_the_log(steps: list[dict[str, Any]]) -> None:
    # update-function-code and get-function-configuration return the environment variables,
    # two of which are secrets, so their output must always be narrowed.
    checked = 0
    for step in steps:
        for line in step.get("run", "").replace("\\\n", " ").splitlines():
            if "aws lambda update-function-code" in line or "get-function-configuration" in line:
                assert "--query" in line, step.get("name")
                checked += 1
    assert checked >= 2  # the update and the failure diagnosis


def test_the_image_is_smoke_tested_before_it_is_pushed(steps: list[dict[str, Any]]) -> None:
    names = [s.get("name", "") for s in steps]
    assert names.index("Smoke-test image") < names.index("Push image")


def test_no_user_controlled_text_is_interpolated_into_shell(steps: list[dict[str, Any]]) -> None:
    for step in steps:
        assert "${{" not in step.get("run", ""), step.get("name")  # values go through env: instead


def test_every_action_is_pinned_to_a_major_version(steps: list[dict[str, Any]]) -> None:
    for step in steps:
        if "uses" in step:
            assert "@v" in step["uses"], step["uses"]


def test_the_deploy_does_not_run_on_pull_requests(workflow: dict[str, Any]) -> None:
    assert "pull_request" not in workflow["on"] and "pull_request_target" not in workflow["on"]
