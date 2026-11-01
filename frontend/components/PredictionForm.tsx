"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { LuMousePointerClick, LuSparkles, LuZap } from "react-icons/lu";
import Alert from "@/components/ui/Alert";
import Select from "@/components/ui/Select";
import { errorMessage, predict } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { notifyError, notifyPromise } from "@/lib/notifications";
import type {
  FeatureSpec,
  FeatureValue,
  PredictionResponse,
  RegisteredModel,
} from "@/lib/types";
import { buttonClass, cardClass, fieldClass } from "@/lib/ui";
import { cn } from "@/lib/utils";

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
        className={fieldClass}
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
      <Select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">(leave blank)</option>
        {options.map(([optionValue, label]) => (
          <option key={optionValue} value={optionValue}>
            {label}
          </option>
        ))}
      </Select>
    );
  } else {
    input = (
      <input
        id={id}
        type="text"
        maxLength={200}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={fieldClass}
      />
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="flex items-baseline justify-between gap-2 text-sm font-medium">
        <span className="break-all">{spec.name}</span>
        <span className="shrink-0 text-xs font-normal text-muted">
          {spec.value_type === "number" ? "number" : spec.value_type === "boolean" ? "true/false" : "text"}
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

function predictionText(prediction: PredictionResponse["predictions"][number] | undefined): string {
  return typeof prediction === "number" ? formatNumber(prediction, 4) : String(prediction);
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
      notifyError("Prediction input is invalid", built.error);
      return;
    }
    setSubmitting(true);
    try {
      setResult(
        await notifyPromise(predict(model.model_id, [built.instance]), {
          loading: "Running the prediction",
          success: "Prediction ready",
          successDescription: (response) =>
            `Predicted ${model.target_column}: ${predictionText(response.predictions[0])}`,
          error: "Prediction failed",
        }),
      );
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
    <section aria-labelledby="predict-title" className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 id="predict-title" className="text-2xl font-semibold tracking-tight">
          Try a prediction
        </h2>
        <p className="text-sm text-muted">
          A blank field is sent as missing; the model fills it with a typical value from its
          training data.
        </p>
      </div>
      {!approved && (
        <Alert tone="warning">
          {model.approval_status === "REVOKED"
            ? "This model's approval was revoked, so it cannot make predictions."
            : "Approve this model to enable predictions."}
        </Alert>
      )}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
        <form onSubmit={submit} className={cn(cardClass, "rounded-2xl p-6 lg:col-span-7")}>
          <fieldset disabled={!approved || submitting} className="flex flex-col gap-5">
            <legend className="sr-only">Feature values</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              {model.feature_schema.map((spec) => (
                <FeatureInput
                  key={spec.name}
                  spec={spec}
                  value={values[spec.name] ?? ""}
                  onChange={(next) => setValues((current) => ({ ...current, [spec.name]: next }))}
                />
              ))}
            </div>
            {error && <Alert role="alert">{error}</Alert>}
            <div>
              <button type="submit" className={buttonClass("primary")}>
                <LuZap aria-hidden="true" className="size-4" />
                {submitting ? "Predicting…" : "Predict"}
              </button>
            </div>
          </fieldset>
        </form>

        <div
          role="status"
          aria-live="polite"
          className={cn(cardClass, "rounded-2xl p-6 lg:sticky lg:top-24 lg:col-span-5")}
        >
          {result ? (
            <div className="flex flex-col gap-5">
              <div className="flex items-center gap-2 text-sm font-medium text-success">
                <LuSparkles aria-hidden="true" className="size-4" />
                Prediction
              </div>
              <p className="flex flex-col gap-1">
                <span className="text-sm text-muted">Predicted {model.target_column}:</span>
                <strong className="text-4xl font-semibold tracking-tight break-all tabular-nums">
                  {predictionText(prediction)}
                </strong>
              </p>
              {probabilities && (
                <table className="w-full text-sm">
                  <caption className="sr-only">Class probabilities</caption>
                  <thead className="text-xs text-muted">
                    <tr>
                      <th scope="col" className="pb-2 text-left font-medium">Class</th>
                      <th scope="col" className="pb-2 text-right font-medium">Probability</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(probabilities)
                      .sort((a, b) => b[1] - a[1])
                      .map(([label, probability], index) => (
                        <tr key={label}>
                          <th scope="row" className="py-1.5 pr-4 text-left font-medium">
                            <span className="break-all">{label}</span>
                            <span aria-hidden="true" className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-surface">
                              <motion.span
                                className={cn("block h-full rounded-full", index === 0 ? "bg-accent" : "bg-text/25")}
                                initial={{ width: 0 }}
                                animate={{ width: `${probability * 100}%` }}
                                transition={{ type: "spring", stiffness: 120, damping: 22 }}
                              />
                            </span>
                          </th>
                          <td className="py-1.5 text-right align-top tabular-nums">
                            {(probability * 100).toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              )}
              <p className="border-t border-border/60 pt-4 text-xs text-muted">
                Model version {result.model_version}
                {result.request_id ? ` · request ${result.request_id}` : ""}
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-8 text-center text-muted">
              <span
                aria-hidden="true"
                className="flex size-12 items-center justify-center rounded-2xl bg-surface text-text/60"
              >
                <LuMousePointerClick className="size-5" />
              </span>
              <p className="text-sm">The prediction will appear here.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
