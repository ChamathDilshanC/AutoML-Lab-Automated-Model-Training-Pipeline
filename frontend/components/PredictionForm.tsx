"use client";

import { useState } from "react";
import { errorMessage, predict } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type {
  FeatureSpec,
  FeatureValue,
  PredictionResponse,
  RegisteredModel,
} from "@/lib/types";

/** The input for one feature, chosen from the model's feature schema. */
function FeatureInput({
  spec,
  value,
  onChange,
}: {
  spec: FeatureSpec;
  value: string;
  onChange: (next: string) => void;
}) {
  const id = `feature-${spec.name}`;
  const field = "rounded-md border border-border bg-bg px-3 py-2";

  let input: React.ReactNode;
  if (spec.value_type === "number") {
    input = (
      <input
        id={id}
        type="number"
        step="any"
        inputMode="decimal"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={field}
      />
    );
  } else if (spec.value_type === "boolean" || spec.categories) {
    const options =
      spec.value_type === "boolean"
        ? [
            ["true", "True"],
            ["false", "False"],
          ]
        : (spec.categories ?? []).map((category) => [category, category]);
    input = (
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={field}
      >
        <option value="">(leave blank)</option>
        {options.map(([optionValue, label]) => (
          <option key={optionValue} value={optionValue}>
            {label}
          </option>
        ))}
      </select>
    );
  } else {
    input = (
      <input
        id={id}
        type="text"
        maxLength={200}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={field}
      />
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-medium">
        {spec.name}{" "}
        <span className="text-sm font-normal text-muted">
          ({spec.value_type === "number" ? "number" : spec.value_type === "boolean" ? "true/false" : "text"})
        </span>
      </label>
      {input}
    </div>
  );
}

/** Convert what the user typed into the JSON value the API expects. Blank means "missing". */
function toInstance(
  schema: FeatureSpec[],
  values: Record<string, string>,
): { instance: Record<string, FeatureValue> } | { error: string } {
  const instance: Record<string, FeatureValue> = {};
  for (const spec of schema) {
    const raw = (values[spec.name] ?? "").trim();
    if (raw === "") {
      instance[spec.name] = null;
    } else if (spec.value_type === "number") {
      const number = Number(raw);
      if (!Number.isFinite(number)) return { error: `"${spec.name}" must be a number.` };
      instance[spec.name] = number;
    } else if (spec.value_type === "boolean") {
      instance[spec.name] = raw === "true";
    } else {
      instance[spec.name] = values[spec.name];
    }
  }
  return { instance };
}

export default function PredictionForm({ model }: { model: RegisteredModel }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<PredictionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const approved = model.approval_status === "APPROVED";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    // Text a number input cannot parse (for example "1e999") makes the browser's own form
    // validation block this submit, so it is never silently sent as a missing value.
    const built = toInstance(model.feature_schema, values);
    if ("error" in built) {
      setError(built.error);
      return;
    }
    setSubmitting(true);
    try {
      setResult(await predict(model.model_id, [built.instance]));
    } catch (err) {
      setResult(null);
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const prediction = result?.predictions[0];
  const probabilities = result?.probabilities?.[0];

  return (
    <section aria-labelledby="predict-title" className="flex flex-col gap-4">
      <h2 id="predict-title" className="text-xl font-semibold">
        Try a prediction
      </h2>
      {!approved && (
        <p className="rounded-md border border-warning p-3">
          <span aria-hidden="true">○ </span>
          Approve this model to enable predictions.
        </p>
      )}
      <form onSubmit={submit} className="flex flex-col gap-4">
        <fieldset disabled={!approved || submitting} className="flex flex-col gap-4">
          <legend className="sr-only">Feature values</legend>
          {model.feature_schema.map((spec) => (
            <FeatureInput
              key={spec.name}
              spec={spec}
              value={values[spec.name] ?? ""}
              onChange={(next) => setValues((current) => ({ ...current, [spec.name]: next }))}
            />
          ))}
          <p className="text-sm text-muted">
            A blank field is sent as missing; the model fills it with a typical value from its
            training data.
          </p>
          <div>
            <button
              type="submit"
              className="rounded-md bg-accent px-4 py-2 font-medium text-on-accent disabled:opacity-60"
            >
              {submitting ? "Predicting…" : "Predict"}
            </button>
          </div>
        </fieldset>
      </form>

      {error && (
        <p role="alert" className="rounded-md border border-danger p-3 text-danger">
          {error}
        </p>
      )}

      <div role="status" aria-live="polite">
        {result && (
          <div className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4">
            <p>
              Predicted {model.target_column}:{" "}
              <strong className="text-2xl">
                {typeof prediction === "number" ? formatNumber(prediction, 4) : String(prediction)}
              </strong>
            </p>
            {probabilities && (
              <table className="text-sm">
                <caption className="sr-only">Class probabilities</caption>
                <thead>
                  <tr>
                    <th scope="col" className="pr-4 text-left">Class</th>
                    <th scope="col" className="text-right">Probability</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(probabilities)
                    .sort((a, b) => b[1] - a[1])
                    .map(([label, probability]) => (
                      <tr key={label}>
                        <th scope="row" className="pr-4 text-left font-medium">{label}</th>
                        <td className="text-right tabular-nums">{(probability * 100).toFixed(1)}%</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
            <p className="text-sm text-muted">
              Model version {result.model_version}
              {result.request_id ? ` · request ${result.request_id}` : ""}
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
