import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../lib/AuthContext";

/** ログアウト状態では /login へ戻す。 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p style={{ padding: 24 }}>読み込み中…</p>;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}
