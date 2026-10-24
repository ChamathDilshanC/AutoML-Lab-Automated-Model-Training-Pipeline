# ADR 0004 — Local accounts with bearer tokens

- **Status:** Accepted for local and self-hosted use (implemented in M7). The identity provider for a cloud deployment is still **Open**.
- **Date:** 2026-10-24

## Context
Before M7 every request was attributed to one placeholder owner, so ownership checks existed but protected nothing. The architecture brief calls for "a maintained authentication solution" and leaves the provider open (a managed AWS service is one candidate, but cost and eligibility are unchecked and M6 comes later). The project needs real sign-in now so that the AWS work starts from a secure base.

## Decision
1. **Accounts** live in a local `users` table. There is **no public sign-up**: accounts are created by an operator with `python -m app.cli create-user`.
2. **Passwords** are hashed with scrypt from the Python standard library (per-user random salt, parameters stored with the hash), must be 12 to 128 characters, and are compared in constant time. Signing in with an unknown username performs the same work as a wrong password and gets the same answer.
3. **Sessions** are signed JWTs (HS256) sent as `Authorization: Bearer`. The signing key is `SECRET_KEY` (at least 32 characters). It is mandatory unless `ENVIRONMENT` is `local`, where a random per-process key is used instead and a warning is logged. The accepted algorithm is pinned, and `exp`, `iat` and `sub` are required. Tokens last 60 minutes.
4. **Every request re-reads the user**, so disabling or deleting an account stops its tokens at once instead of at expiry.
5. **Authorisation** is ownership only: every `/api/v1` route except sign-in sits behind one router-level dependency, and repositories filter by the caller's user ID. A foreign ID gets the same `404` as a missing one. There are no roles.
6. **The browser** keeps the token in `sessionStorage` and sends it as a bearer header. A `401` from any call clears it and sends the user to `/login`.
7. **Abuse limits:** sign-in is limited per client address and predictions per user, with an in-memory token bucket.

## Consequences
- **Positive:** no extra services or paid dependencies; simple to test (an automated test walks every route and checks that it needs a token); tokens and passwords never need a third party.
- **Negative, accepted for now:**
  - **No server-side logout.** A leaked token works until it expires, because signing out only removes the browser's copy. Disabling the user is the emergency stop.
  - **`sessionStorage` is readable by any script on the page**, so an XSS bug would expose the token. The app renders no untrusted HTML. An httpOnly cookie with CSRF protection, or a backend-for-frontend, would be stronger.
  - **No password reset, password change, MFA or account lockout.** The sign-in rate limit is the only brute-force defence.
  - **Rate limits are per process.** Several API processes multiply them, and behind a proxy every client shares the proxy's address.
- **Revisit when moving to AWS (M6/M8):** a managed identity provider (for example Cognito) would replace the local `users` table and give hosted password reset and MFA; the router-level dependency and the ownership filter would stay as they are.

## Related
[Security § 3 and § 15](../SECURITY.md) · [API spec § 4.0](../API_SPEC.md) · [ADR 0002](0002-trusted-joblib-artifacts.md)
