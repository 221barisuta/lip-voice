import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/AuthContext";
import { getPhrases } from "../lib/api";
import { loginWithGoogle, logout } from "../lib/auth";

export function Login() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user && !busy) return <Navigate to="/speak" replace />;

  const onClick = async () => {
    setBusy(true);
    setError("");
    try {
      await loginWithGoogle();
      await getPhrases(); // 初回ログイン時に users/{uid} と初期フレーズをサーバーが作る
      nav("/speak", { replace: true });
    } catch (e) {
      await logout().catch(() => undefined);
      setError(e instanceof Error && e.message.includes("403")
        ? "このアカウントは許可されていません"
        : "ログインできませんでした。もう一度お試しください");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
      <div style={{ textAlign: "center" }}>
        <h1>lip-voice</h1>
        <button onClick={onClick} disabled={busy} style={{ fontSize: 24, padding: "16px 32px" }}>
          Googleでログイン
        </button>
        {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      </div>
    </main>
  );
}
