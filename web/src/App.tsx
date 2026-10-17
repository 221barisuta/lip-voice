import { Navigate, Route, Routes } from "react-router-dom";
import { Collect } from "./screens/Collect";
import { SpeakPlaceholder } from "./screens/SpeakPlaceholder";

export function App() {
  return (
    <Routes>
      <Route path="/collect" element={<Collect />} />
      <Route path="/speak" element={<SpeakPlaceholder />} />
      <Route path="*" element={<Navigate to="/collect" replace />} />
    </Routes>
  );
}
