import { clearToken, getToken } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/config";
import type {
  ApiErrorBody,
  Dataset,
  Experiment,
  ExperimentCreate,
  ExperimentOptions,
  FeatureValue,
  CurrentUser,
  DatasetUpload,
  Leaderboard,
  PredictionResponse,
  RegisteredModel,
  TokenResponse,
  UploadTarget,
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

const LOGIN_PATH = "/api/v1/auth/login";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch (err) {
    if (init?.signal?.aborted) throw err;
    throw new ApiRequestError("Could not reach the server.", 0);
  }
  // A 401 on any other call means the token expired or was revoked: sign out locally.
  if (response.status === 401 && token && path !== LOGIN_PATH) clearToken();
  const text = await response.text();
  if (!response.ok) throw toError(response.status, text);
  if (response.status === 204 || text === "") return undefined as T;
  return JSON.parse(text) as T;
}

export function login(username: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>(LOGIN_PATH, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });
}

export function googleLogin(accessToken: string): Promise<TokenResponse> {
  return request<TokenResponse>("/api/v1/auth/google", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token: accessToken }),
  });
}

export function getMe(signal?: AbortSignal): Promise<CurrentUser> {
  return request<CurrentUser>("/api/v1/auth/me", { signal });
}

export function deleteDataset(datasetId: string): Promise<void> {
  return request<void>(`/api/v1/datasets/${encodeURIComponent(datasetId)}`, { method: "DELETE" });
}

export function revokeModel(modelId: string): Promise<RegisteredModel> {
  return request<RegisteredModel>(`/api/v1/models/${encodeURIComponent(modelId)}/revoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true }),
  });
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

export function listModels(signal?: AbortSignal): Promise<RegisteredModel[]> {
  return request<RegisteredModel[]>("/api/v1/models", { signal });
}

export function getModel(modelId: string, signal?: AbortSignal): Promise<RegisteredModel> {
  return request<RegisteredModel>(`/api/v1/models/${encodeURIComponent(modelId)}`, { signal });
}

export function approveModel(modelId: string): Promise<RegisteredModel> {
  return request<RegisteredModel>(`/api/v1/models/${encodeURIComponent(modelId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true }),
  });
}

export function predict(
  modelId: string,
  instances: Record<string, FeatureValue>[],
): Promise<PredictionResponse> {
  return request<PredictionResponse>(`/api/v1/models/${encodeURIComponent(modelId)}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instances }),
  });
}

/** Step 1: tell the API about the file and get the target to send its bytes to. */
export function registerDataset(file: File): Promise<DatasetUpload> {
  return request<DatasetUpload>("/api/v1/datasets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, size_bytes: file.size }),
  });
}

/**
 * Step 2: send the file to the target, with progress (fetch cannot report upload progress).
 *
 * A presigned storage URL is signed for exactly these headers and must not get the bearer token,
 * which would both break the signature and hand a credential to another host. Only a target on
 * this API (`requires_auth`) receives it.
 */
export function sendFile(
  target: UploadTarget,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(target.method, target.requires_auth ? `${API_BASE_URL}${target.url}` : target.url);
    for (const [name, value] of Object.entries(target.headers)) xhr.setRequestHeader(name, value);
    if (target.requires_auth) {
      const token = getToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onerror = () =>
      reject(
        new ApiRequestError(
          target.requires_auth
            ? "Could not reach the server."
            : "The upload could not be sent to storage. Check your connection and the bucket's CORS settings.",
          0,
        ),
      );
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else if (target.requires_auth) {
        if (xhr.status === 401) clearToken();
        reject(toError(xhr.status, xhr.responseText));
      } else {
        // Storage answers in XML that can name the bucket; show a fixed message instead.
        reject(new ApiRequestError(`Storage refused the upload (status ${xhr.status}).`, xhr.status));
      }
    };
    xhr.send(file);
  });
}
