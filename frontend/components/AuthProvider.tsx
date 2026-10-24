"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";
import { errorMessage, getMe, login } from "@/lib/api";
import { clearToken, getToken, setToken, subscribe } from "@/lib/auth";

export type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error"; message: string }
  | { status: "authenticated"; username: string };

interface AuthContextValue {
  auth: AuthState;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>.");
  return value;
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  // undefined while rendering on the server and during hydration, when sessionStorage is unknown.
  const token = useSyncExternalStore<string | null | undefined>(subscribe, getToken, () => undefined);
  const [me, setMe] = useState<{ token: string; username: string } | null>(null);
  const [failure, setFailure] = useState<{ token: string; message: string } | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    getMe()
      .then((user) => {
        if (!cancelled) setMe({ token, username: user.username });
      })
      .catch((err) => {
        // A 401 has already signed the user out (see lib/api.ts). Anything else, such as the
        // server being down, must not sign them out: show an error with a retry instead.
        if (!cancelled && getToken()) setFailure({ token, message: errorMessage(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [token, attempt]);

  let auth: AuthState;
  if (token === undefined) auth = { status: "loading" };
  else if (token === null) auth = { status: "anonymous" };
  else if (me?.token === token) auth = { status: "authenticated", username: me.username };
  else if (failure?.token === token) auth = { status: "error", message: failure.message };
  else auth = { status: "loading" };

  const value: AuthContextValue = {
    auth,
    signIn: async (username, password) => {
      const { access_token } = await login(username, password);
      setToken(access_token);
    },
    signOut: () => clearToken(),
    retry: () => {
      setFailure(null);
      setAttempt((n) => n + 1);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
