import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { setUnauthorizedHandler } from "../api/client";
import { getCurrentUser, login as loginRequest, logout as logoutRequest } from "../api/endpoints";
import { AuthContext, type AuthState } from "./authContext";

/**
 * Owns "who is signed in".
 *
 * There is no token to store: the session is an HttpOnly cookie the browser attaches for us. So
 * the only way to answer "am I signed in?" on a fresh page load is to ask the server — hence the
 * `/auth/me` probe on mount. That also means a session revoked from the CLI takes effect on the
 * next request, with nothing stale cached here.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthState>(undefined);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((me) => !cancelled && setUser(me))
      // A 401 here is the expected "not signed in" answer, not an error worth surfacing.
      .catch(() => !cancelled && setUser(null));
    return () => {
      cancelled = true;
    };
  }, []);

  // Any 401 from anywhere in the app — an expired session, or one revoked from the CLI — drops
  // us to the login screen. Registered once, centrally, rather than handled per call site.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      // Only an interrupted session earns the explanation. A 401 while already signed out is
      // just a failed login attempt, and "your session expired" would be a lie there.
      setUser((current) => {
        if (current) setSessionExpired(true);
        return null;
      });
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const me = await loginRequest({ username, password });
    setSessionExpired(false);
    setUser(me);
  }, []);

  const signOut = useCallback(async () => {
    // Clear locally even if the request fails: the cookie may already be gone, and leaving the
    // user staring at a signed-in UI they can't use is the worse outcome.
    //
    // Swallowed rather than rethrown (a `finally` would clear the user and still reject): callers
    // are fire-and-forget click handlers with no recovery to attempt, so rethrowing only buys an
    // unhandled rejection in the console.
    try {
      await logoutRequest();
    } catch {
      // Already signed out as far as this tab is concerned.
    }
    // Signing out on purpose is not an interrupted session — no explanation is owed.
    setSessionExpired(false);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, sessionExpired, signIn, signOut }),
    [user, sessionExpired, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
