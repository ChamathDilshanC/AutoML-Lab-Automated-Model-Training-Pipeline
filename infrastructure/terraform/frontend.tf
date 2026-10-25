# The frontend on AWS Amplify Hosting, built from frontend/ in the GitHub repository on every push to
# amplify_branch (docs/ADR/0007). Created only when enable_frontend is true.
#
# Amplify documents Next.js support for versions 12 to 15 and lists streaming as unsupported; this
# app is on Next.js 16 and streams with <Suspense>. Check the first build and the pages before
# pointing users at it (docs/DEPLOYMENT.md).
#
# Terraform does not start a build. After the first apply, start one from the Amplify console or with
# `aws amplify start-job --app-id <id> --branch-name <branch> --job-type RELEASE`, and again whenever
# the API URL changes: NEXT_PUBLIC_API_BASE_URL is inlined into the browser bundle at build time.

locals {
  amplify_origin = var.enable_frontend ? "https://${var.amplify_branch}.${aws_amplify_app.frontend[0].default_domain}" : null

  # Every browser origin that may call the API and upload to the bucket: the ones given in
  # frontend_origins (for example a Vercel project) plus the Amplify branch, when there is one.
  frontend_origins = distinct(concat(var.frontend_origins, var.enable_frontend ? [local.amplify_origin] : []))
}

resource "aws_amplify_app" "frontend" {
  count = var.enable_frontend ? 1 : 0

  name       = "${var.name_prefix}-frontend"
  repository = "https://github.com/${var.github_repository}"
  platform   = "WEB_COMPUTE" # Next.js server-side rendering

  # Used once, to connect the repository through the Amplify GitHub App; Amplify does not keep it,
  # but the Terraform state does. Later applies do not need it.
  access_token = var.amplify_github_token

  # The app lives in frontend/; Node 24 matches CI.
  build_spec = <<-EOT
    version: 1
    applications:
      - appRoot: frontend
        frontend:
          phases:
            preBuild:
              commands:
                - nvm install 24
                - npm ci
            build:
              commands:
                - npm run build
          artifacts:
            baseDirectory: .next
            files:
              - '**/*'
          cache:
            paths:
              - node_modules/**/*
              - .next/cache/**/*
  EOT

  environment_variables = {
    AMPLIFY_MONOREPO_APP_ROOT = "frontend"
  }

  lifecycle {
    ignore_changes = [access_token]
  }
}

resource "aws_amplify_branch" "frontend" {
  count = var.enable_frontend ? 1 : 0

  app_id            = aws_amplify_app.frontend[0].id
  branch_name       = var.amplify_branch
  framework         = "Next.js - SSR"
  stage             = "PRODUCTION"
  enable_auto_build = true

  # Without compute there is no API URL yet; the app then falls back to its local default.
  environment_variables = var.enable_compute ? { NEXT_PUBLIC_API_BASE_URL = local.api_url } : {}
}
