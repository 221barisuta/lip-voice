import { Navigate, Route, Routes } from "react-router-dom";
import { Collect } from "./screens/Collect";
import { Data } from "./screens/Data";
import { Report } from "./screens/Report";
import { Speak } from "./screens/Speak";

export function App() {
  return (
    <Routes>
      <Route path="/collect" element={<Collect />} />
      <Route path="/speak" element={<Speak />} />
      <Route path="/report" element={<Report />} />
      <Route path="/data" element={<Data />} />
      <Route path="*" element={<Navigate to="/collect" replace />} />
    </Routes>
  );
}
