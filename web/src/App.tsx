import { Navigate, Route, Routes } from "react-router-dom";
import { Collect } from "./screens/Collect";
import { Report } from "./screens/Report";
import { Speak } from "./screens/Speak";

export function App() {
  return (
    <Routes>
      <Route path="/collect" element={<Collect />} />
      <Route path="/speak" element={<Speak />} />
      <Route path="/report" element={<Report />} />
      <Route path="*" element={<Navigate to="/collect" replace />} />
    </Routes>
  );
}
