// Where the access token lives.
//
// It is kept in sessionStorage: gone when the tab closes, not shared between tabs, and not sent
// anywhere by the browser on its own (unlike a cookie). Any script on the page can still read it,
// so the app must never render untrusted HTML. Tokens last one hour by default.

const KEY = "automl.access_token";
const listeners = new Set<() => void>();
let memoryToken: string | null = null; // used if sessionStorage is unavailable

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

function notify() {
  listeners.forEach((listener) => listener());
}

export function setToken(token: string): void {
  memoryToken = token;
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    // Keep going with the in-memory copy.
  }
  notify();
}

export function clearToken(): void {
  memoryToken = null;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // Nothing to clear.
  }
  notify();
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Only follow redirects to a path on this site, never to another origin. */
export function safeNextPath(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  return next;
}
