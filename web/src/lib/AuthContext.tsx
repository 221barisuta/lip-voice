import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { User } from "firebase/auth";
import { watchAuth } from "./auth";

interface AuthState { user: User | null; loading: boolean }
const Ctx = createContext<AuthState>({ user: null, loading: true });
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, loading: true });
  useEffect(() => watchAuth((user) => setState({ user, loading: false })), []);
  return <Ctx.Provider value={state}>{children}</Ctx.Provider>;
}
