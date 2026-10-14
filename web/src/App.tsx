import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./components/RequireAuth";
import { Collect } from "./screens/Collect";
import { Login } from "./screens/Login";
import { SpeakPlaceholder } from "./screens/SpeakPlaceholder";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/speak" element={<RequireAuth><SpeakPlaceholder /></RequireAuth>} />
      <Route path="/collect" element={<RequireAuth><Collect /></RequireAuth>} />
      <Route path="*" element={<Navigate to="/speak" replace />} />
    </Routes>
  );
}
