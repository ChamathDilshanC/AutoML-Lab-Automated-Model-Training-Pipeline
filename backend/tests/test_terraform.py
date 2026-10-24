"""Static checks of the Terraform in infrastructure/terraform.

These parse the files and check the security-relevant settings. They create nothing and need no
AWS account or Terraform binary. CI additionally runs `terraform fmt`, `init` and `validate`.
"""

from typing import Any

import hcl2
import pytest

from app.core.config import Settings
from tests.hclutil import INFRA, blocks, load, one, policy_actions, variables


@pytest.fixture(scope="module")
def main() -> dict[str, Any]:
    return load("main.tf")


@pytest.fixture(scope="module")
def queues() -> dict[str, Any]:
    return load("queue.tf")


def test_every_terraform_file_parses() -> None:
    files = sorted(INFRA.glob("*.tf"))
    assert {f.name for f in files} >= {
        "versions.tf",
        "variables.tf",
        "main.tf",
        "queue.tf",
        "iam.tf",
        "outputs.tf",
    }
    for file in files:
        assert hcl2.loads(file.read_text(encoding="utf-8")), file.name


def test_the_bucket_is_private_and_encrypted(main: dict[str, Any]) -> None:
    access = blocks(main, "resource", "aws_s3_bucket_public_access_block")["artifacts"]
    for setting in (
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ):
        assert access[setting] is True, setting

    encryption = blocks(main, "resource", "aws_s3_bucket_server_side_encryption_configuration")
    rule = one(encryption["artifacts"]["rule"])
    assert one(rule["apply_server_side_encryption_by_default"])["sse_algorithm"] == "AES256"

    ownership = blocks(main, "resource", "aws_s3_bucket_ownership_controls")["artifacts"]
    assert one(ownership["rule"])["object_ownership"] == "BucketOwnerEnforced"


def test_the_bucket_refuses_plain_http(main: dict[str, Any]) -> None:
    policy = blocks(main, "data", "aws_iam_policy_document")["bucket_tls_only"]
    statement = one(policy["statement"])
    assert statement["effect"] == "Deny"
    condition = one(statement["condition"])
    assert condition["variable"] == "aws:SecureTransport" and condition["values"] == ["false"]
    attached = blocks(main, "resource", "aws_s3_bucket_policy")["artifacts"]
    assert "bucket_tls_only" in attached["policy"]


def test_cors_allows_browser_uploads_only_from_the_configured_origins(main: dict[str, Any]) -> None:
    config = blocks(main, "resource", "aws_s3_bucket_cors_configuration")["artifacts"]
    rule = one(config["cors_rule"])
    # The local origin plus the deployed frontend's origins; never a literal "*".
    assert (
        rule["allowed_origins"] == "${distinct(concat(var.allowed_origins, var.frontend_origins))}"
    )
    assert set(rule["allowed_methods"]) == {"PUT", "GET", "HEAD"}
    assert rule["allowed_headers"] == ["Content-Type"]
    default = variables(load("variables.tf"))["allowed_origins"]["default"]
    assert default == ["http://localhost:3000"]


def test_unfinished_multipart_uploads_are_cleaned_up(main: dict[str, Any]) -> None:
    config = blocks(main, "resource", "aws_s3_bucket_lifecycle_configuration")["artifacts"]
    rule = one(config["rule"])
    assert rule["status"] == "Enabled"
    assert one(rule["abort_incomplete_multipart_upload"])["days_after_initiation"] == 1


def test_the_queue_is_encrypted_long_polling_and_has_a_dead_letter_queue(
    queues: dict[str, Any],
) -> None:
    found = blocks(queues, "resource", "aws_sqs_queue")
    main_queue, dead = found["experiments"], found["dead_letter"]
    assert main_queue["sqs_managed_sse_enabled"] is True and dead["sqs_managed_sse_enabled"] is True
    assert main_queue["receive_wait_time_seconds"] == 20  # long polling
    assert main_queue["visibility_timeout_seconds"] == "${var.job_timeout_seconds}"
    assert "aws_sqs_queue.dead_letter.arn" in main_queue["redrive_policy"]
    assert "var.max_receive_count" in main_queue["redrive_policy"]
    # A message must stay in the dead-letter queue at least as long as it could sit in the queue.
    assert dead["message_retention_seconds"] >= main_queue["message_retention_seconds"]
    assert ".fifo" not in main_queue["name"]  # a standard queue, see ADR 0005


def test_the_queue_refuses_plain_http(queues: dict[str, Any]) -> None:
    policy = blocks(queues, "data", "aws_iam_policy_document")["queue_tls_only"]
    condition = one(one(policy["statement"])["condition"])
    assert condition["variable"] == "aws:SecureTransport" and condition["values"] == ["false"]


def test_the_visibility_timeout_default_matches_the_applications_job_timeout() -> None:
    default = variables(load("variables.tf"))["job_timeout_seconds"]["default"]
    assert default == Settings().job_timeout_seconds


@pytest.mark.parametrize("label", ["api", "worker"])
def test_application_policies_have_no_wildcards_and_no_unscoped_resources(label: str) -> None:
    body = blocks(load("iam.tf"), "data", "aws_iam_policy_document")[label]
    assert body["statement"]
    for statement in body["statement"]:
        assert statement.get("effect", "Allow") == "Allow"
        assert all(a != "*" and not a.endswith(":*") for a in statement["actions"]), statement[
            "sid"
        ]
        # Every resource is the bucket, the queue, or a folder inside the bucket.
        for resource in statement["resources"]:
            assert resource != "*"
            assert (
                "aws_s3_bucket.artifacts.arn" in resource
                or "aws_sqs_queue.experiments.arn" in resource
            )


def test_the_combined_policy_only_merges_the_two_runtime_policies() -> None:
    body = blocks(load("iam.tf"), "data", "aws_iam_policy_document")["local_dev"]
    assert "statement" not in body  # it adds nothing of its own
    assert body["source_policy_documents"] == [
        "${data.aws_iam_policy_document.api.json}",
        "${data.aws_iam_policy_document.worker.json}",
    ]


def test_only_the_api_can_send_jobs_and_only_the_worker_can_receive_them() -> None:
    api, worker = policy_actions("api"), policy_actions("worker")
    assert "sqs:SendMessage" in api and not {"sqs:ReceiveMessage", "sqs:DeleteMessage"} & api
    assert {"sqs:ReceiveMessage", "sqs:DeleteMessage"} <= worker and "sqs:SendMessage" not in worker


def test_the_worker_cannot_touch_datasets_except_to_read_them() -> None:
    document = blocks(load("iam.tf"), "data", "aws_iam_policy_document")["worker"]
    for statement in document["statement"]:
        on_datasets = any("/datasets/" in r for r in statement["resources"])
        if on_datasets:
            assert statement["actions"] == ["s3:GetObject"], statement["sid"]


def test_nothing_secret_is_created_or_committed() -> None:
    everything = "\n".join(f.read_text(encoding="utf-8") for f in INFRA.glob("*.tf"))
    assert "aws_iam_access_key" not in everything and "aws_iam_user" not in everything
    for needle in ("AKIA", "aws_secret", 'password = "'):
        assert needle not in everything  # no literal key or password anywhere
    assert not list(INFRA.glob("*.tfstate*")) and not list(INFRA.glob("terraform.tfvars"))


def test_the_provider_and_terraform_versions_are_constrained() -> None:
    block = one(load("versions.tf")["terraform"])
    assert block["required_version"].startswith(">=")
    assert one(block["required_providers"])["aws"]["source"] == "hashicorp/aws"
