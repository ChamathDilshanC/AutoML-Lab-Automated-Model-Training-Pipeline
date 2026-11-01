# ADR 0010 - Google sign-in with Supabase Auth

- **Status:** Accepted and implemented
- **Date:** 2026-10-30
- **Supersedes:** The cloud identity-provider choice in [ADR 0004](0004-local-accounts-and-bearer-tokens.md)

## Context

The deployed UI needs a low-maintenance Google-only sign-in flow without storing Google
credentials or adding a second application session system. Existing ownership checks and the
application's short-lived bearer tokens are already tested and should not change.

## Decision

The browser starts Supabase Auth's Google authorization endpoint and receives the provider access
token in the URL fragment. It immediately removes the fragment and sends the token once to
`POST /api/v1/auth/google`. The API verifies `aud=authenticated`, `sub`, `email`, `exp`, issuer
and a configured HS256 secret or pinned RS256/ES256 key from a local JWKS JSON value. It never
fetches keys during a request. The API then creates or reuses a local user keyed by the Supabase
subject and issues the existing application bearer token.

Password login remains available by default for local development and can be disabled with
`PASSWORD_LOGIN_ENABLED=false`. Production disables it. `DAILY_EXPERIMENT_LIMIT` limits new
experiments in a rolling 24-hour window; an idempotency replay is always allowed.

## Consequences

Supabase is used for Auth only; datasets, ownership and application sessions remain local to the
API database. The JWKS/secret and issuer are deployment configuration, never fetched or committed.
Google handles password recovery and MFA. The browser does not persist the Supabase token.

## Manual setup

Create a Supabase project, configure a Google OAuth Web client with the Supabase callback URL,
enable Google in Supabase Auth, and add the deployed `/login` URL to the redirect allow-list.
Supply the project URL and JWT secret (or JWKS) to the deployment through its secret manager.
