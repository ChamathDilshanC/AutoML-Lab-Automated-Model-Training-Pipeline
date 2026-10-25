"""Static checks of the deployment Terraform (M8): network, database, compute, deploy role, budget.

Like test_terraform.py these parse the files; nothing is created and no AWS account is needed.
CI additionally runs the real `terraform validate`.
"""

import textwrap
from typing import Any

import pytest
import yaml

from tests.hclutil import INFRA, blocks, load, one, variables


@pytest.fixture(scope="module")
def database() -> dict[str, Any]:
    return load("database.tf")


@pytest.fixture(scope="module")
def network() -> dict[str, Any]:
    return load("network.tf")


@pytest.fixture(scope="module")
def tfvars() -> dict[str, Any]:
    return variables(load("variables.tf"))


def _all_text() -> str:
    return "\n".join(f.read_text(encoding="utf-8") for f in sorted(INFRA.glob("*.tf")))


def test_the_database_is_private_encrypted_and_protected(database: dict[str, Any]) -> None:
    db = blocks(database, "resource", "aws_db_instance")["main"]
    assert db["publicly_accessible"] is False
    assert db["storage_encrypted"] is True
    assert db["engine"] == "postgres"
    assert db["deletion_protection"] == "${var.db_deletion_protection}"
    assert db["multi_az"] is False  # a single instance keeps this inside the small budget
    assert "manage_master_user_password" not in db


def test_the_database_defaults_to_the_free_tier_class_and_protection(
    tfvars: dict[str, Any],
) -> None:
    assert tfvars["db_instance_class"]["default"] == "db.t4g.micro"
    assert tfvars["db_deletion_protection"]["default"] is True
    assert tfvars["db_skip_final_snapshot"]["default"] is False
    assert tfvars["db_backup_retention_days"]["default"] >= 1


def test_the_database_requires_tls(database: dict[str, Any]) -> None:
    group = blocks(database, "resource", "aws_db_parameter_group")["main"]
    parameter = one(group["parameter"])
    assert parameter["name"] == "rds.force_ssl" and parameter["value"] == "1"
    db = blocks(database, "resource", "aws_db_instance")["main"]
    assert db["parameter_group_name"] == "${aws_db_parameter_group.main.name}"


def test_the_database_lives_in_private_subnets_only(
    database: dict[str, Any], network: dict[str, Any]
) -> None:
    group = blocks(database, "resource", "aws_db_subnet_group")["main"]
    assert group["subnet_ids"] == "${aws_subnet.private[*].id}"
    private_route = blocks(network, "resource", "aws_route_table")["private"]
    assert "route" not in private_route  # no internet route, no NAT


def test_only_the_api_and_the_worker_may_reach_the_database(database: dict[str, Any]) -> None:
    rules = blocks(database, "resource", "aws_vpc_security_group_ingress_rule")
    assert set(rules) == {"database_from_api", "database_from_worker"}
    sources = {r["referenced_security_group_id"] for r in rules.values()}
    assert sources == {"${aws_security_group.api.id}", "${aws_security_group.worker.id}"}
    for rule in rules.values():
        assert rule["from_port"] == rule["to_port"] == 5432
        assert "cidr_ipv4" not in rule  # never open to an address range


def test_the_api_and_the_worker_accept_no_inbound_traffic(database: dict[str, Any]) -> None:
    ingress = blocks(database, "resource", "aws_vpc_security_group_ingress_rule")
    targets = {r["security_group_id"] for r in ingress.values()}
    assert targets == {"${aws_security_group.database.id}"}
    for name in ("api", "worker"):
        group = blocks(database, "resource", "aws_security_group")[name]
        assert "ingress" not in group


def test_there_is_no_nat_gateway_and_no_open_database_port(network: dict[str, Any]) -> None:
    text = _all_text()
    assert "aws_nat_gateway" not in text and "aws_eip" not in text
    assert "0.0.0.0/0" in text  # the public route and the worker's HTTPS egress
    for rule in blocks(
        load("database.tf"), "resource", "aws_vpc_security_group_egress_rule"
    ).values():
        if rule.get("cidr_ipv4") == "0.0.0.0/0":
            assert rule["from_port"] == rule["to_port"] == 443


def test_availability_zones_are_not_looked_up(
    network: dict[str, Any], tfvars: dict[str, Any]
) -> None:
    # Some organizations deny ec2:DescribeAvailabilityZones, which that data source calls.
    assert "aws_availability_zones" not in _all_text()
    assert tfvars["availability_zones"]["default"] is None
    assert "${var.region}a" in network["locals"][0]["azs"]
    subnets = blocks(network, "resource", "aws_subnet")
    for subnet in subnets.values():
        assert subnet["availability_zone"] == "${local.azs[count.index]}"


def test_the_api_reaches_aws_through_vpc_endpoints(network: dict[str, Any]) -> None:
    endpoints = blocks(network, "resource", "aws_vpc_endpoint")
    assert endpoints["s3"]["vpc_endpoint_type"] == "Gateway"
    assert endpoints["sqs"]["vpc_endpoint_type"] == "Interface"
    assert endpoints["sqs"]["private_dns_enabled"] is True
    assert endpoints["sqs"]["service_name"].endswith(".sqs")


def test_secrets_are_generated_and_never_typed_into_a_file() -> None:
    secrets = blocks(load("secrets.tf"), "resource", "aws_ssm_parameter")
    assert {p["type"] for p in secrets.values()} == {"SecureString"}
    for parameter in secrets.values():  # generated, never typed into a file
        assert parameter["value"].startswith("${random_password.")
    ref = load("api.tf")["locals"][0]
    # The worker reads them by reference; the shared settings never carry them.
    assert set(ref["app_secrets"]) == {"DB_PASSWORD", "SECRET_KEY"}
    env = ref["app_environment"]
    assert "DB_PASSWORD" not in env and "SECRET_KEY" not in env
    assert env["ENVIRONMENT"] == "production" and env["DB_SSLMODE"] == "require"
    assert env["STORAGE_MODE"] == "s3" and env["JOB_MODE"] == "sqs"
    # The Lambda API cannot reach Parameter Store (no NAT, no SSM endpoint; docs/ADR/0007), so it
    # gets the same generated values, which never appear as literals.
    lambda_env = ref["lambda_environment"]
    assert "DB_PASSWORD = random_password.db.result" in lambda_env
    assert "SECRET_KEY = random_password.jwt_secret.result" in lambda_env


def test_the_lambda_environment_never_sets_the_reserved_region_variable() -> None:
    # Lambda sets AWS_REGION itself and rejects a function that sets it.
    lambda_env = load("api.tf")["locals"][0]["lambda_environment"]
    assert 'for name, value in local.app_environment : name => value if name != "AWS_REGION"' in (
        lambda_env
    )
    assert "AWS_REGION =" not in lambda_env


def test_the_container_roles_carry_exactly_the_m6_policies() -> None:
    api_role = blocks(load("api.tf"), "resource", "aws_iam_role_policy_attachment")["api"]
    assert api_role["policy_arn"] == "${aws_iam_policy.api.arn}"
    worker_role = blocks(load("worker.tf"), "resource", "aws_iam_role_policy_attachment")["worker"]
    assert worker_role["policy_arn"] == "${aws_iam_policy.worker.arn}"
    # The API may not be the worker and the worker may not be the API.
    assert "aws_iam_policy.worker" not in load("api.tf").get("resource", [{}]).__repr__()
    assert "aws_iam_policy.api" not in load("worker.tf").get("resource", [{}]).__repr__()


def test_compute_is_off_until_asked_for_and_the_worker_starts_stopped(
    tfvars: dict[str, Any],
) -> None:
    assert tfvars["enable_compute"]["default"] is False
    assert tfvars["worker_desired_count"]["default"] == 0
    function = blocks(load("api.tf"), "resource", "aws_lambda_function")["api"]
    assert function["count"] == "${var.enable_compute ? 1 : 0}"
    worker = blocks(load("worker.tf"), "resource", "aws_ecs_service")["worker"]
    assert worker["count"] == "${var.enable_compute ? 1 : 0}"
    assert worker["desired_count"] == "${var.worker_desired_count}"


def _resources(prefix: str) -> dict[str, Any]:
    return {
        f"{kind}.{label}": body
        for path in sorted(INFRA.glob("*.tf"))
        for entry in load(path.name).get("resource", [])
        for kind, labelled in entry.items()
        if kind.startswith(prefix)
        for label, body in labelled.items()
    }


def test_app_runner_is_gone_and_lambda_and_amplify_are_switched_by_their_variables(
    tfvars: dict[str, Any],
) -> None:
    # App Runner is closed to new customers (docs/ADR/0007), so nothing may still create it.
    assert not _resources("aws_apprunner_")
    lambdas = _resources("aws_lambda_")
    assert set(lambdas) == {
        "aws_lambda_function.api",
        "aws_lambda_function_url.api",
        "aws_lambda_permission.api_url",
        "aws_lambda_permission.api_url_invoke",
    }
    for address, body in lambdas.items():
        assert body["count"] == "${var.enable_compute ? 1 : 0}", address
    amplify = _resources("aws_amplify_")
    assert set(amplify) == {"aws_amplify_app.frontend", "aws_amplify_branch.frontend"}
    for address, body in amplify.items():
        assert body["count"] == "${var.enable_frontend ? 1 : 0}", address
    assert tfvars["enable_frontend"]["default"] is False


def test_the_api_runs_in_the_private_subnets_behind_the_api_security_group() -> None:
    function = blocks(load("api.tf"), "resource", "aws_lambda_function")["api"]
    vpc = one(function["vpc_config"])
    assert vpc["subnet_ids"] == "${aws_subnet.private[*].id}"  # no public address, no NAT needed
    assert vpc["security_group_ids"] == ["${aws_security_group.api.id}"]
    assert function["package_type"] == "Image"
    assert one(function["image_config"])["command"] == ["api"]
    # The deploy workflow owns which image runs; an apply must not roll it back.
    assert one(function["lifecycle"])["ignore_changes"] == ["image_uri"]


def test_the_url_is_public_but_the_function_cannot_be_invoked_directly() -> None:
    api = load("api.tf")
    url = blocks(api, "resource", "aws_lambda_function_url")["api"]
    assert url["authorization_type"] == "NONE"  # the application checks the bearer token
    assert "cors" not in url  # FastAPI answers CORS; two layers would send conflicting headers
    permissions = blocks(api, "resource", "aws_lambda_permission")
    by_action = {p["action"]: p for p in permissions.values()}
    assert set(by_action) == {"lambda:InvokeFunctionUrl", "lambda:InvokeFunction"}
    assert by_action["lambda:InvokeFunctionUrl"]["function_url_auth_type"] == "NONE"
    # Without this condition principal "*" could call the Invoke API and skip the URL.
    assert by_action["lambda:InvokeFunction"]["invoked_via_function_url"] is True


def test_the_api_role_is_for_lambda_only_and_no_longer_reads_parameter_store() -> None:
    api = load("api.tf")
    role = blocks(api, "resource", "aws_iam_role")
    assert set(role) == {"api"}  # the App Runner image-pull role is gone
    assert '{Service = "lambda.amazonaws.com"}' in role["api"]["assume_role_policy"]
    assert "apprunner" not in role["api"]["assume_role_policy"]
    attachments = blocks(api, "resource", "aws_iam_role_policy_attachment")
    assert {a["policy_arn"] for a in attachments.values()} == {
        "${aws_iam_policy.api.arn}",
        "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole",
    }
    inline = blocks(api, "resource", "aws_iam_role_policy")
    assert set(inline) == {"api_image_pull"}  # no read_secrets: the values arrive in the env
    pull = one(blocks(api, "data", "aws_iam_policy_document")["api_image_pull"]["statement"])
    assert pull["actions"] == ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    assert pull["resources"] == ["${aws_ecr_repository.backend.arn}"]


def test_amplify_builds_the_frontend_folder_and_gets_the_api_url() -> None:
    frontend = load("frontend.tf")
    app = blocks(frontend, "resource", "aws_amplify_app")["frontend"]
    assert app["platform"] == "WEB_COMPUTE"
    assert app["repository"] == "https://github.com/${var.github_repository}"
    assert app["environment_variables"] == {"AMPLIFY_MONOREPO_APP_ROOT": "frontend"}
    spec_text = app["build_spec"].removeprefix("<<-EOT").removesuffix("EOT")
    spec = yaml.safe_load(textwrap.dedent(spec_text))
    (application,) = spec["applications"]
    assert application["appRoot"] == "frontend"
    assert application["frontend"]["artifacts"]["baseDirectory"] == ".next"
    branch = blocks(frontend, "resource", "aws_amplify_branch")["frontend"]
    assert "NEXT_PUBLIC_API_BASE_URL = local.api_url" in branch["environment_variables"]
    token = variables(load("variables.tf"))["amplify_github_token"]
    assert token["sensitive"] is True and token["default"] is None  # never in a file


def test_a_shell_into_the_worker_is_off_unless_asked_for(tfvars: dict[str, Any]) -> None:
    assert tfvars["enable_ecs_exec"]["default"] is False
    worker = load("worker.tf")
    exec_policy = blocks(worker, "resource", "aws_iam_role_policy")["worker_exec"]
    assert exec_policy["count"] == "${var.enable_ecs_exec ? 1 : 0}"
    service = blocks(worker, "resource", "aws_ecs_service")["worker"]
    assert service["enable_execute_command"] == "${var.enable_ecs_exec}"


def test_the_worker_task_runs_the_worker_command_with_secrets_by_reference() -> None:
    task = blocks(load("worker.tf"), "resource", "aws_ecs_task_definition")["worker"]
    assert task["requires_compatibilities"] == ["FARGATE"]
    assert task["network_mode"] == "awsvpc"
    definition = task["container_definitions"]
    assert 'command   = ["worker"]' in definition or '"worker"' in definition
    assert "valueFrom" in definition and "local.app_secrets" in definition


def test_the_api_cors_comes_from_the_frontend_origins() -> None:
    env = load("api.tf")["locals"][0]["api_environment"]
    assert env["CORS_ORIGINS"] == "${jsonencode(local.frontend_origins)}"
    assert env["TRUSTED_PROXY_HOPS"] == "${tostring(var.trusted_proxy_hops)}"
    # The given origins plus the Amplify branch, and nothing else (never "*").
    origins = load("frontend.tf")["locals"][0]["frontend_origins"]
    assert origins == (
        "${distinct(concat(var.frontend_origins,"
        " var.enable_frontend ? [local.amplify_origin] : []))}"
    )


def test_frontend_origins_must_be_origins_not_urls_with_paths(tfvars: dict[str, Any]) -> None:
    assert tfvars["frontend_origins"]["default"] == []
    assert "validation" in tfvars["frontend_origins"]


def test_the_deploy_role_trusts_only_this_repository_and_environment() -> None:
    trust = blocks(load("cicd.tf"), "data", "aws_iam_policy_document")["github_trust"]
    statement = one(trust["statement"])
    assert statement["actions"] == ["sts:AssumeRoleWithWebIdentity"]
    conditions = {c["variable"]: c for c in statement["condition"]}
    audience = conditions["token.actions.githubusercontent.com:aud"]
    assert audience["test"] == "StringEquals" and audience["values"] == ["sts.amazonaws.com"]
    subject = conditions["token.actions.githubusercontent.com:sub"]
    assert subject["test"] == "StringEquals"  # exact match, never StringLike with a wildcard
    (value,) = subject["values"]
    assert value == "repo:${var.github_repository}:environment:${var.github_environment}"
    assert "*" not in value


def test_the_repository_variable_has_no_default(tfvars: dict[str, Any]) -> None:
    assert "default" not in tfvars["github_repository"]
    assert "default" not in tfvars["budget_alert_email"]


def test_the_deploy_role_can_only_push_one_repository_and_roll_out_two_services() -> None:
    policy = blocks(load("cicd.tf"), "data", "aws_iam_policy_document")["deploy"]
    by_sid = {s["sid"]: s for s in policy["statement"]}
    assert set(by_sid) == {"EcrLogin", "EcrPush", "ApiRollOut", "WorkerRollOut"}
    for sid, statement in by_sid.items():
        assert all(a != "*" and not a.endswith(":*") for a in statement["actions"]), sid
        if sid != "EcrLogin":
            assert "*" not in "".join(r for r in statement["resources"] if not r.endswith("/*")), (
                sid
            )
    assert by_sid["EcrLogin"]["actions"] == ["ecr:GetAuthorizationToken"]  # cannot be scoped
    assert by_sid["EcrPush"]["resources"] == ["${aws_ecr_repository.backend.arn}"]
    forbidden = {"iam:PassRole", "iam:CreateRole", "ecr:DeleteRepository", "ecs:RunTask"}
    assert not forbidden & {a for s in by_sid.values() for a in s["actions"]}


def test_the_budget_is_ten_dollars_monthly_and_emails_before_and_after() -> None:
    budget = blocks(load("budget.tf"), "resource", "aws_budgets_budget")["monthly"]
    assert budget["time_unit"] == "MONTHLY" and budget["limit_unit"] == "USD"
    assert budget["limit_amount"] == "${tostring(var.budget_limit_usd)}"
    assert variables(load("variables.tf"))["budget_limit_usd"]["default"] == 10
    notifications = budget["notification"]
    kinds = {(n["notification_type"], n["threshold"]) for n in notifications}
    assert ("ACTUAL", 100) in kinds and ("FORECASTED", 100) in kinds and ("ACTUAL", 80) in kinds
    for notification in notifications:
        assert notification["subscriber_email_addresses"] == ["${var.budget_alert_email}"]


def test_the_image_repository_scans_and_keeps_a_bounded_history() -> None:
    repo = blocks(load("ecr.tf"), "resource", "aws_ecr_repository")["backend"]
    assert one(repo["image_scanning_configuration"])["scan_on_push"] is True
    lifecycle = blocks(load("ecr.tf"), "resource", "aws_ecr_lifecycle_policy")["backend"]
    assert "expire" in lifecycle["policy"] and "imageCountMoreThan" in lifecycle["policy"]


def test_providers_are_pinned_to_versions_that_have_the_resources_used() -> None:
    providers = one(one(load("versions.tf")["terraform"])["required_providers"])
    # OIDC thumbprints became optional in 5.81; invoked_via_function_url arrived in 6.28.
    assert providers["aws"]["version"] == ">= 6.28"
    assert providers["random"]["source"] == "hashicorp/random"
