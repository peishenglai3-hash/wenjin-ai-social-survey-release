import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useApp } from "../hooks/useApp";
import { getErrorMessage } from "../utils/errors";

/**
 * ORCID OAuth callback page — receives auth_code from backend redirect,
 * exchanges it for JWT tokens, then redirects to the app.
 *
 * URL: /orcid-callback?auth_code=<code>&redirect_to=<path>
 */
export default function OrcidCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { orcidExchange } = useApp();
  const authCode = searchParams.get("auth_code");
  const redirectTo = searchParams.get("redirect_to") || "/";
  const [error, setError] = useState(authCode ? "" : "Missing auth_code parameter from ORCID callback");

  useEffect(() => {
    if (!authCode) {
      return;
    }

    orcidExchange(authCode)
      .then(() => {
        navigate(redirectTo, { replace: true });
      })
      .catch((error: unknown) => {
        setError(getErrorMessage(error, "ORCID 登录失败，请重试"));
      });
  }, [authCode, redirectTo, navigate, orcidExchange]);

  if (error) {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ textAlign: "center" }}>
          <h2>ORCID 登录失败</h2>
          <p style={{ color: "var(--text-muted)", margin: "16px 0" }}>{error}</p>
          <button className="btn-primary" onClick={() => navigate("/login", { replace: true })}>
            返回登录
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <h2>正在通过 ORCID 登录…</h2>
        <p style={{ color: "var(--text-muted)", marginTop: 12 }}>
          请稍候，正在验证学术身份
        </p>
      </div>
    </div>
  );
}
