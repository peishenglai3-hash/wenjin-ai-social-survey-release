import { Navigate, Outlet } from "react-router-dom";
import { useApp } from "../hooks/useApp";

interface Props {
  requireAdmin?: boolean;
  children?: React.ReactNode;
}

export default function ProtectedRoute({ requireAdmin = false, children }: Props) {
  const { isAuthenticated, isAuthLoading, user } = useApp();

  if (isAuthLoading) {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ textAlign: "center" }}>
          <p>加载中…</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requireAdmin && user?.role !== "admin") {
    return <Navigate to="/" replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}
