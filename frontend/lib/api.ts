import { API_BASE_URL } from "@/lib/config";
import type {
  ApiErrorBody,
  Dataset,
  Experiment,
  ExperimentCreate,
  ExperimentOptions,
  Leaderboard,
  ValidationReport,
} from "@/lib/types";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function toError(status: number, bodyText: string): ApiRequestError {
  try {
    const { error } = JSON.parse(bodyText) as ApiErrorBody;
    return new ApiRequestError(error.message, status, error.request_id ?? undefined);
  } catch {
    return new ApiRequestError(`Request failed (${status}).`, status);
  }
}

/** Text safe to show a user, including the request ID support can search for. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiRequestError) {
    return err.requestId ? `${err.message} (request ${err.requestId})` : err.message;
  }
  return "Something went wrong. Please try again.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (err) {
    if (init?.signal?.aborted) throw err;
    throw new ApiRequestError("Could not reach the server.", 0);
  }
  const text = await response.text();
  if (!response.ok) throw toError(response.status, text);
  return JSON.parse(text) as T;
}

export function getDataset(datasetId: string, signal?: AbortSignal): Promise<Dataset> {
  return request<Dataset>(`/api/v1/datasets/${encodeURIComponent(datasetId)}`, { signal });
}

export function validateDataset(datasetId: string): Promise<ValidationReport> {
  return request<ValidationReport>(
    `/api/v1/datasets/${encodeURIComponent(datasetId)}/validate`,
    { method: "POST" },
  );
}

export function getExperimentOptions(signal?: AbortSignal): Promise<ExperimentOptions> {
  return request<ExperimentOptions>("/api/v1/experiments/options", { signal });
}

/** The idempotency key makes a double submit return the same experiment instead of two. */
export function createExperiment(
  payload: ExperimentCreate,
  idempotencyKey: string,
): Promise<Experiment> {
  return request<Experiment>("/api/v1/experiments", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(payload),
  });
}

export function getExperiment(experimentId: string, signal?: AbortSignal): Promise<Experiment> {
  return request<Experiment>(`/api/v1/experiments/${encodeURIComponent(experimentId)}`, { signal });
}

export function getLeaderboard(experimentId: string, signal?: AbortSignal): Promise<Leaderboard> {
  return request<Leaderboard>(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/results`,
    { signal },
  );
}

/** Upload with progress reporting (fetch cannot report upload progress). */
export function uploadDataset(
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<Dataset> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/api/v1/datasets`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ApiRequestError("Could not reach the server.", 0));
    xhr.onload = () => {
      if (xhr.status === 201) {
        resolve(JSON.parse(xhr.responseText) as Dataset);
      } else {
        reject(toError(xhr.status, xhr.responseText));
      }
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
