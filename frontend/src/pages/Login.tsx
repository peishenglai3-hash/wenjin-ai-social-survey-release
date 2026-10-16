import { useState, type FormEvent, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useApp } from "../hooks/useApp";
import { fetchCaptcha } from "../api/captcha";
import { getErrorMessage } from "../utils/errors";

type AuthTab = "email" | "phone" | "guest";

export default function Login() {
  const { login, loginPhone, sendSmsCode, loginGuest, orcidLogin, isAuthenticated } = useApp();
  const navigate = useNavigate();

  const [tab, setTab] = useState<AuthTab>("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [smsCode, setSmsCode] = useState("");
  const [smsSent, setSmsSent] = useState(false);
  const [smsCountdown, setSmsCountdown] = useState(0);
  const [sendingSms, setSendingSms] = useState(false);
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaSvg, setCaptchaSvg] = useState("");
  const [captchaAnswer, setCaptchaAnswer] = useState("");
  const [captchaLoading, setCaptchaLoading] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [guestLoading, setGuestLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) navigate("/", { replace: true });
  }, [isAuthenticated, navigate]);

  const loadCaptcha = async () => {
    setCaptchaLoading(true);
    try {
      const data = await fetchCaptcha();
      setCaptchaToken(data.captcha_token);
      setCaptchaSvg(data.svg);
    } catch {
      setError("验证码加载失败，请重试");
    } finally {
      setCaptchaLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "phone") void Promise.resolve().then(loadCaptcha);
  }, [tab]);

  useEffect(() => {
    if (smsCountdown <= 0) return;
    const t = setTimeout(() => setSmsCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [smsCountdown]);

  const handleSendSms = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setError("请输入有效的11位手机号");
      return;
    }
    if (!captchaAnswer.trim()) {
      setError("请输入图形验证码");
      return;
    }
    setError("");
    setSendingSms(true);
    try {
      await sendSmsCode(phone, captchaToken, captchaAnswer.trim());
      setSmsSent(true);
      setSmsCountdown(60);
      setCaptchaAnswer("");
      loadCaptcha();
    } catch (error: unknown) {
      setError(getErrorMessage(error, "发送验证码失败"));
      loadCaptcha();
      setCaptchaAnswer("");
    } finally {
      setSendingSms(false);
    }
  };

  const handleEmailLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (error: unknown) {
      setError(getErrorMessage(error, "登录失败，请重试"));
    } finally {
      setLoading(false);
    }
  };

  const handlePhoneLogin = async (e: FormEvent) => {
    e.preventDefault();
    if (!smsSent) { setError("请先获取短信验证码"); return; }
    if (smsCode.length !== 6) { setError("请输入6位短信验证码"); return; }
    setError("");
    setLoading(true);
    try {
      await loginPhone(phone, smsCode);
      navigate("/", { replace: true });
    } catch (error: unknown) {
      setError(getErrorMessage(error, "登录失败，请重试"));
    } finally {
      setLoading(false);
    }
  };

  // ── Guest mode ──
  const handleGuestLogin = async () => {
    setGuestLoading(true);
    setError("");
    try {
      loginGuest();
      navigate("/", { replace: true });
    } catch {
      setError("游客模式启动失败，请重试");
    } finally {
      setGuestLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>问津</h1>
          <p className="auth-subtitle">AI 社会调查工作台 — 登录</p>
        </div>

        <div className="auth-tabs">
          <button className={`auth-tab ${tab === "phone" ? "active" : ""}`}
            onClick={() => setTab("phone")}>
            📱 手机号登录
          </button>
          <button className={`auth-tab ${tab === "email" ? "active" : ""}`}
            onClick={() => setTab("email")}>
            📧 邮箱登录
          </button>
        </div>

        {error && <div className="form-error">{error}</div>}

        {tab === "email" ? (
          <form onSubmit={handleEmailLogin}>
            <div className="form-group">
              <label htmlFor="email">邮箱</label>
              <input id="email" type="text" inputMode="email" value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.invalid" required autoFocus />
            </div>
            <div className="form-group">
              <label htmlFor="password">密码</label>
              <input id="password" type="password" value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="········" required />
            </div>
            <button type="submit" className="btn-primary" disabled={loading}
              style={{ width: "100%", marginTop: 8 }}>
              {loading ? "登录中…" : "登录"}
            </button>
          </form>
        ) : (
          <form onSubmit={handlePhoneLogin}>
            <div className="form-group">
              <label htmlFor="phone">手机号</label>
              <input id="phone" type="tel" value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
                placeholder="请输入11位手机号" required autoFocus maxLength={11} />
            </div>

            <div className="form-group">
              <label>图形验证码</label>
              <div className="captcha-row">
                <div className="captcha-svg-container">
                  {captchaLoading ? <div className="captcha-loading">加载中…</div>
                    : <div className="captcha-svg" dangerouslySetInnerHTML={{ __html: captchaSvg }}
                        onClick={loadCaptcha} title="点击刷新验证码" />}
                </div>
                <button type="button" className="btn-secondary btn-sm"
                  onClick={loadCaptcha} disabled={captchaLoading}>↻</button>
              </div>
              <input id="captchaAnswer" type="text" value={captchaAnswer}
                onChange={(e) => setCaptchaAnswer(e.target.value)}
                placeholder="输入图中的字母和数字" required maxLength={6}
                autoComplete="off" style={{ marginTop: 8 }} />
            </div>

            <div className="form-group">
              <label>短信验证码</label>
              <div style={{ display: "flex", gap: 8 }}>
                <input id="smsCode" type="text" value={smsCode}
                  onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="6位数字" required maxLength={6}
                  autoComplete="one-time-code" style={{ flex: 1 }} />
                <button type="button" className="btn-secondary"
                  onClick={handleSendSms} disabled={sendingSms || smsCountdown > 0}
                  style={{ whiteSpace: "nowrap", minWidth: 120 }}>
                  {sendingSms ? "发送中…"
                    : smsCountdown > 0 ? `${smsCountdown}秒后重发`
                    : smsSent ? "重新发送" : "获取验证码"}
                </button>
              </div>
            </div>

            <button type="submit" className="btn-primary" disabled={loading}
              style={{ width: "100%", marginTop: 8 }}>
              {loading ? "登录中…" : "登录"}
            </button>
          </form>
        )}

        <p className="auth-footer">
          没有帐号？<Link to="/register">注册新帐号</Link>
        </p>

        {/* ── ORCID Academic Login ── */}
        <div style={{
          marginTop: 20, paddingTop: 16,
          borderTop: "1px dashed var(--border)",
        }}>
          <button
            onClick={orcidLogin}
            style={{
              width: "100%", padding: "10px 0", fontSize: 14, fontWeight: 600,
              background: "#A6CE39", color: "#fff", border: "none", borderRadius: 6,
              cursor: "pointer", display: "flex", alignItems: "center",
              justifyContent: "center", gap: 8,
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
              <path d="M12 0C5.37 0 0 5.37 0 12s5.37 12 12 12 12-5.37 12-12S18.63 0 12 0zM6.5 6.5h3v11h-3v-11zm5 0h3v11h-3v-11z"/>
            </svg>
            Sign in with ORCID
          </button>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 10, textAlign: "center", lineHeight: 1.5 }}>
            使用 ORCID 学术身份登录<br />无需密码，通过 ORCID 验证
          </p>
        </div>

        {/* ── Guest / Tourist Mode ── */}
        <div style={{
          marginTop: 20, paddingTop: 16,
          borderTop: "1px dashed var(--border)",
        }}>
          <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", marginBottom: 10 }}>
            只想看看？以游客身份浏览，无需注册
          </p>
          <button
            onClick={handleGuestLogin}
            disabled={guestLoading}
            className="btn-secondary"
            style={{
              width: "100%", padding: "10px 0",
              fontSize: 14, fontWeight: 500,
              background: "var(--surface)", color: "var(--text-muted)",
              border: "1px dashed var(--border)",
            }}
          >
            {guestLoading ? "进入中…" : "👋 游客体验"}
          </button>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 10, textAlign: "center", lineHeight: 1.5 }}>
            游客可浏览示例项目和公共案例<br />
            创建项目或导出数据需注册帐号
          </p>
        </div>
      </div>
    </div>
  );
}
