# ADR 0002 — Trusted joblib artifacts only

- **Status:** Proposed (derived from the security guidance in the architecture brief)
- **Date:** 2026-10-24

## Context
Model artifacts are saved with `joblib`, which uses pickle. Loading a pickle can execute arbitrary code. The prediction service must load artifacts, so loading an attacker-controlled file would be a remote-code-execution risk.

## Decision
1. Artifacts are produced only by the project's own trusted worker code; users can never upload a model.
2. Write access to the model storage prefix is limited to the worker's role.
3. The prediction service loads only artifacts that are registered and approved in the metadata store.
4. Dependencies are pinned, and each artifact's metadata records library versions so incompatible loads are detected.
5. Model versions are immutable once registered.

## Consequences
- **Positive:** simple, standard scikit-learn persistence with a clear trust boundary.
- **Negative:** artifacts are tied to library versions; changing storage permissions or adding user-supplied models would require a new decision (for example a safer serialisation format or sandboxed loading).

## Related
[Security § 2](../SECURITY.md#2-threats-and-controls) · [Architecture § 6.7](../ARCHITECTURE.md#67-prediction-service)
