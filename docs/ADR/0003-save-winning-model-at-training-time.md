# ADR 0003 — Save the winning model at training time

- **Status:** Accepted (decision by the maintainer, 2026-10-24); implemented in M5
- **Date:** 2026-10-24

## Context
After an experiment ranks its candidates, the registry (M5) needs the winning fitted pipeline. There were two options: save the pipeline while training, or keep only the recorded configuration and retrain on demand.

Retraining would not reliably reproduce the evaluated model. Library versions or hardware can change the result, so the registered model could differ from the one whose test metrics the leaderboard shows. It would also repeat compute that was already spent.

## Decision
1. The worker keeps each fitted pipeline in memory until the experiment is ranked, then serialises only the winner with `joblib` and saves it through the storage adapter to `models/{model_id}/{version}/model.joblib`, next to a `metadata.json` (feature schema, preprocessing, metrics, split, seed, library versions; no data rows). The other pipelines are discarded.
2. The saved model is exactly the pipeline that was evaluated: it is fitted on the training split only and is **not** refit on the test rows, so the reported metrics describe it.
3. The SHA-256 of the artifact is stored in the database and verified before every load ([ADR 0002](0002-trusted-joblib-artifacts.md)).
4. Saving happens before the experiment is marked `SUCCEEDED`. If it fails, partial files are removed and the experiment is `FAILED` ("The winning model could not be saved."), so a succeeded experiment always has a model.
5. Each artifact is its own immutable `model_id`. Its `version` counts the artifacts registered for the same owner, dataset, target column and task.
6. A model is only loaded when the installed scikit-learn version equals the one recorded at training time.

## Consequences
- **Positive:** the registered model is exactly what was measured; no repeated compute; the artifact can be inspected and checksummed.
- **Negative:** artifacts take storage (limit `MAX_ARTIFACT_BYTES`, proposed 200 MiB); the model never saw the test rows, so it uses less data than a refit would; models are tied to the scikit-learn version that trained them and must be retrained after an upgrade.
- **Open:** refitting the winner on all rows would be a different model with unmeasured performance. If wanted, it needs its own decision and a new version, not a silent change.

## Related
[Architecture § 6.5 and § 6.7](../ARCHITECTURE.md) · [Security](../SECURITY.md) · [Database schema](../DATABASE_SCHEMA.md)
