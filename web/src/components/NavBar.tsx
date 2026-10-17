import { NavLink } from "react-router-dom";

const link = ({ isActive }: { isActive: boolean }) => ({
  padding: "8px 16px", marginRight: 8, borderRadius: 6, textDecoration: "none", fontSize: 18,
  background: isActive ? "#235" : "#eee", color: isActive ? "#fff" : "#235",
});

export function NavBar({ right }: { right?: string }) {
  return (
    <nav style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
      <div>
        <NavLink to="/collect" style={link}>収集</NavLink>
        <NavLink to="/speak" style={link}>認識（テスト）</NavLink>
        <NavLink to="/report" style={link}>評価</NavLink>
      </div>
      <span>{right}</span>
    </nav>
  );
}
