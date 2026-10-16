import { useState, type FormEvent, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useApp } from "../hooks/useApp";
import { fetchCaptcha } from "../api/captcha";
import { getErrorMessage } from "../utils/errors";

type AuthTab = "email" | "phone";

export default function Register() {
  const { register, registerPhone, sendSmsCode, orcidLogin, isAuthenticated } = useApp();
  const navigate = useNavigate();

  const [tab, setTab] = useState<AuthTab>("phone");

  // ── Email fields ──
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [captchaAnswer, setCaptchaAnswer] = useState("");
  const [captchaToken, setCaptchaToken] = useState("");
  const [captchaSvg, setCaptchaSvg] = useState("");

  // ── Phone fields ──
  const [phone, setPhone] = useState("");
  const [smsCode, setSmsCode] = useState("");
  const [phoneDisplayName, setPhoneDisplayName] = useState("");
  const [smsSent, setSmsSent] = useState(false);
  const [smsCountdown, setSmsCountdown] = useState(0);
  const [sendingSms, setSendingSms] = useState(false);
  const [phoneCaptchaAnswer, setPhoneCaptchaAnswer] = useState("");

  // ── Shared ──
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [captchaLoading, setCaptchaLoading] = useState(false);

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

  useEffect(() => { void Promise.resolve().then(loadCaptcha); }, []);
  useEffect(() => {
    if (isAuthenticated) navigate("/", { replace: true });
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    if (smsCountdown <= 0) return;
    const t = setTimeout(() => setSmsCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [smsCountdown]);

  // ── Email registration ──
  const handleEmailRegister = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!captchaAnswer.trim()) { setError("请输入验证码"); return; }
    if (password.length < 8) { setError("密码至少8位"); return; }
    setLoading(true);
    try {
      await register(email, password, displayName, captchaToken, captchaAnswer.trim());
      navigate("/", { replace: true });
    } catch (error: unknown) {
      setError(getErrorMessage(error, "注册失败，请重试"));
      loadCaptcha();
      setCaptchaAnswer("");
    } finally {
      setLoading(false);
    }
  };

  // ── Phone registration ──
  const handleSendSms = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setError("请输入有效的11位手机号");
      return;
    }
    if (!phoneCaptchaAnswer.trim()) {
      setError("请输入图形验证码");
      return;
    }
    setError("");
    setSendingSms(true);
    try {
      await sendSmsCode(phone, captchaToken, phoneCaptchaAnswer.trim());
      setSmsSent(true);
      setSmsCountdown(60);
      setPhoneCaptchaAnswer("");
      loadCaptcha();
    } catch (error: unknown) {
      setError(getErrorMessage(error, "发送验证码失败"));
      loadCaptcha();
      setPhoneCaptchaAnswer("");
    } finally {
      setSendingSms(false);
    }
  };

  const handlePhoneRegister = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!smsSent) { setError("请先获取短信验证码"); return; }
    if (smsCode.length !== 6) { setError("请输入6位短信验证码"); return; }
    setLoading(true);
    try {
      await registerPhone(phone, smsCode, phoneDisplayName, captchaToken, phoneCaptchaAnswer || captchaAnswer);
      navigate("/", { replace: true });
    } catch (error: unknown) {
      setError(getErrorMessage(error, "注册失败，请重试"));
      loadCaptcha();
      setPhoneCaptchaAnswer("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>问津</h1>
          <p className="auth-subtitle">AI 社会调查工作台 — 注册帐号</p>
        </div>

        <div className="auth-tabs">
          <button className={`auth-tab ${tab === "phone" ? "active" : ""}`}
            onClick={() => setTab("phone")}>
            📱 手机号注册
          </button>
          <button className={`auth-tab ${tab === "email" ? "active" : ""}`}
            onClick={() => setTab("email")}>
            📧 邮箱注册
          </button>
        </div>

        {error && <div className="form-error">{error}</div>}

        {tab === "email" ? (
          <form onSubmit={handleEmailRegister}>
            <div className="form-group">
              <label htmlFor="email">邮箱</label>
              <input id="email" type="email" value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com" required autoFocus />
            </div>
            <div className="form-group">
              <label htmlFor="displayName">显示名称（选填）</label>
              <input id="displayName" type="text" value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="您的称呼" maxLength={100} />
            </div>
            <div className="form-group">
              <label htmlFor="password">密码（至少8位）</label>
              <input id="password" type="password" value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="········" required minLength={8} />
            </div>
            <div className="form-group">
              <label>验证码</label>
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
            <button type="submit" className="btn-primary" disabled={loading}
              style={{ width: "100%", marginTop: 8 }}>
              {loading ? "注册中…" : "注册"}
            </button>
          </form>
        ) : (
          <form onSubmit={handlePhoneRegister}>
            <div className="form-group">
              <label htmlFor="phone">手机号</label>
              <input id="phone" type="tel" value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
                placeholder="请输入11位手机号" required autoFocus maxLength={11} />
            </div>
            <div className="form-group">
              <label htmlFor="phoneDisplayName">显示名称（选填）</label>
              <input id="phoneDisplayName" type="text" value={phoneDisplayName}
                onChange={(e) => setPhoneDisplayName(e.target.value)}
                placeholder="您的称呼" maxLength={100} />
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
              <input id="phoneCaptchaAnswer" type="text" value={phoneCaptchaAnswer}
                onChange={(e) => setPhoneCaptchaAnswer(e.target.value)}
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
              {loading ? "注册中…" : "注册"}
            </button>
          </form>
        )}

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
            Sign up with ORCID
          </button>
          <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 10, textAlign: "center", lineHeight: 1.5 }}>
            使用 ORCID 学术身份一键注册<br />无需邮箱或手机号即可创建帐号
          </p>
        </div>

        <p className="auth-footer">
          已有帐号？<Link to="/login">登录</Link>
        </p>
      </div>
    </div>
  );
}
