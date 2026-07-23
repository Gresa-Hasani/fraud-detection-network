import { NavLink, Outlet } from "react-router-dom";
import "./Layout.css";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/search", label: "Search" },
  { to: "/alerts", label: "Fraud Alerts" },
  { to: "/communities", label: "Fraud Communities" },
  { to: "/investigations", label: "Investigations" },
];

export function Layout() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">Neo4j Fraud Detection Network</div>
        <nav className="app-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => (isActive ? "active" : "")}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
