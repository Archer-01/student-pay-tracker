import { createContext, useContext } from "react";
import type { UserOut } from "../api/types";

/**
 * `undefined` while the initial `/auth/me` probe is in flight, `null` once we know nobody is
 * signed in. The three states are distinct on purpose: rendering the login page during the probe
 * would flash it on every reload for an already-signed-in user.
 */
export type AuthState = UserOut | null | undefined;

export type AuthContextValue = {
  user: AuthState;
  /**
   * True when a signed-in session was cut short (expired, or revoked from the CLI) rather than
   * the user simply arriving signed-out. Drives the explanation on the login page — being bounced
   * to a login form with no reason given is the confusing case worth spending a message on.
   */
  sessionExpired: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
