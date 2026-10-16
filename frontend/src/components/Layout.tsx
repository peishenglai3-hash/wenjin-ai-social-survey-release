import { Outlet, useNavigate } from "react-router-dom";
import { useApp } from "../hooks/useApp";
import Sidebar from "./Sidebar";
import MobileBottomNav from "./MobileBottomNav";
import Copilot from "./Copilot";
import PWAInstallPrompt from "./PWAInstallPrompt";
import config from "../config";

export default function Layout() {
  const { user, isAuthenticated, logout } = useApp();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-body">
        <header className="app-header">
          <h1>{config.appName}</h1>
          <div className="header-auth">
            {isAuthenticated && user ? (
              <>
                <span className="header-user-email" title={user.email}>
                  {user.display_name || user.email}
                </span>
                {user.role === "admin" && (
                  <span className="header-admin-badge">管理员</span>
                )}
                <button
                  className="btn-header-logout"
                  onClick={handleLogout}
                  title="退出登录"
                >
                  退出
                </button>
              </>
            ) : (
              <button
                className="btn-header-login"
                onClick={() => navigate("/login")}
              >
                登录
              </button>
            )}
          </div>
        </header>
        <main className="app-main">
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>v0.4.1 · 问津 · 华中科技大学数字社会研究中心</span>
        </footer>
      </div>
      <MobileBottomNav />
      <Copilot />
      <PWAInstallPrompt />
    </div>
  );
}
