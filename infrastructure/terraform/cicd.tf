# Lets .github/workflows/deploy.yml deploy without any long-lived AWS key: GitHub issues a
# short-lived OIDC token for the job, and AWS exchanges it for temporary credentials of the role
# below, but only for this repository and only for jobs running in the GitHub environment named
# by github_environment (docs/ADR/0006).

locals {
  github_oidc_url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = local.github_oidc_url
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1

  url = local.github_oidc_url
}

locals {
  github_oidc_provider_arn = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    sid       = "GitHubActionsOidc"
    actions   = ["sts:AssumeRoleWithWebIdentity"]
    resources = ["*"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.name_prefix}-github-deploy"
  description          = "Assumed by GitHub Actions to push the backend image and roll out the API and worker."
  assume_role_policy   = data.aws_iam_policy_document.github_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "deploy" {
  # The only action that cannot be limited to one repository: it returns a registry login token.
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  statement {
    sid       = "ApiRollOut"
    actions   = ["apprunner:StartDeployment", "apprunner:ListOperations", "apprunner:DescribeService"]
    resources = ["arn:aws:apprunner:${var.region}:${data.aws_caller_identity.current.account_id}:service/${var.name_prefix}-api/*"]
  }

  statement {
    sid       = "WorkerRollOut"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = ["arn:aws:ecs:${var.region}:${data.aws_caller_identity.current.account_id}:service/${var.name_prefix}-cluster/${var.name_prefix}-worker"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
