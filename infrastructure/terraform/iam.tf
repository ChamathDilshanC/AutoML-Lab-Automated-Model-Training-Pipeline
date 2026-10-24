# Least-privilege policies, one per runtime (docs/SECURITY.md). Nothing here creates an IAM user or
# an access key: keys in Terraform state are secrets. Attach a policy to a user, role or SSO
# permission set that you control (see README.md).
#
# A test (backend/tests/test_aws.py) records every AWS call the application makes and fails if one
# of them is missing from these lists, or if a list grants more than the code can use.

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "ApiObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.artifacts.arn}/datasets/*", "${aws_s3_bucket.artifacts.arn}/models/*"]
  }

  statement {
    sid       = "ApiListOwnFolders"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["datasets/*", "models/*"]
    }
  }

  statement {
    sid       = "ApiSendJobs"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.experiments.arn]
  }
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid       = "WorkerReadDatasets"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/datasets/*"]
  }

  statement {
    sid       = "WorkerWriteModels"
    actions   = ["s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.artifacts.arn}/models/*"]
  }

  statement {
    sid       = "WorkerReceiveJobs"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage"]
    resources = [aws_sqs_queue.experiments.arn]
  }
}

# For running the API and the worker on one machine as one identity (local development).
data "aws_iam_policy_document" "local_dev" {
  source_policy_documents = [
    data.aws_iam_policy_document.api.json,
    data.aws_iam_policy_document.worker.json,
  ]
}

resource "aws_iam_policy" "api" {
  name        = "${var.name_prefix}-api"
  description = "AutoML Lab API: object access under datasets/ and models/, and sending job messages."
  policy      = data.aws_iam_policy_document.api.json
}

resource "aws_iam_policy" "worker" {
  name        = "${var.name_prefix}-worker"
  description = "AutoML Lab worker: read datasets, write models, receive and delete job messages."
  policy      = data.aws_iam_policy_document.worker.json
}

resource "aws_iam_policy" "local_dev" {
  name        = "${var.name_prefix}-local-dev"
  description = "AutoML Lab API and worker together, for one local development identity."
  policy      = data.aws_iam_policy_document.local_dev.json
}
