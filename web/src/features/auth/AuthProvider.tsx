import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { session } from "../../lib/session";
import { userSchema, type AuthSession, type User } from "./schemas";

type AuthContextValue = {
  user: User | null;
  authenticated: boolean;
  complete: (value: AuthSession) => void;
  syncUser: (value: User) => void;
  logout: () => void;
};

const USER_KEY = "gatehouse_user";
const AuthContext = createContext<AuthContextValue | null>(null);

function savedUser(): User | null {
  try {
    const value = sessionStorage.getItem(USER_KEY);
    return value ? userSchema.parse(JSON.parse(value)) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => (session.get() ? savedUser() : null));
  const complete = useCallback((auth: AuthSession) => {
    session.set(auth.token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(auth.user));
    setUser(auth.user);
  }, []);
  const syncUser = useCallback((nextUser: User) => {
    sessionStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    setUser(nextUser);
  }, []);
  const logout = useCallback(() => {
    session.clear();
    sessionStorage.removeItem(USER_KEY);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      authenticated: Boolean(user && session.get()),
      complete,
      syncUser,
      logout,
    }),
    [complete, logout, syncUser, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
