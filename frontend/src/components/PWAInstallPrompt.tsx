import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

/**
 * PWAInstallPrompt — mobile PWA installation helper
 *
 * Detects three scenarios and offers appropriate guidance:
 * 1. WeChat / Weixin in-app browser → overlay guiding to system browser
 * 2. iOS Safari (no beforeinstallprompt) → bottom banner showing "Add to Home Screen"
 * 3. Android Chrome (beforeinstallprompt) → floating install button
 *
 * WeChat detection is critical for fieldwork: WeChat's WKWebView blocks
 * getUserMedia, making in-app recording impossible.
 */

export default function PWAInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [isWeChat] = useState(() => navigator.userAgent.toLowerCase().includes("micromessenger"));
  const [isIOS] = useState(() => /iphone|ipad|ipod/i.test(navigator.userAgent));
  const [isStandalone, setIsStandalone] = useState(() => window.matchMedia("(display-mode: standalone)").matches);
  const [dismissedWeChat, setDismissedWeChat] = useState(false);
  const [dismissedIOS, setDismissedIOS] = useState(false);

  useEffect(() => {
    // beforeinstallprompt listener (Chrome on Android)
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);

    const installedHandler = () => {
      setDeferredPrompt(null);
      setIsStandalone(true);
    };
    window.addEventListener("appinstalled", installedHandler);

    return () => {
      window.removeEventListener("beforeinstallprompt", handler);
      window.removeEventListener("appinstalled", installedHandler);
    };
  }, []);

  // Already installed — nothing to show
  if (isStandalone) return null;

  // ── 1. WeChat in-app browser — blocking overlay ──
  if (isWeChat && !dismissedWeChat) {
    return (
      <div className="pwa-wechat-overlay">
        <div className="pwa-wechat-dialog">
          <div className="pwa-wechat-icon" aria-hidden="true">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <rect width="48" height="48" rx="12" fill="#1E3A8A" />
              <path
                d="M14 24l7 7 13-13"
                stroke="#fff"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <h3 className="pwa-wechat-title">请在系统浏览器中打开</h3>
          <p className="pwa-wechat-body">
            微信内置浏览器不支持录音功能。
            <br />
            请点击右上角
            <strong>「···」</strong>
            &nbsp;→&nbsp;
            <strong>「在浏览器中打开」</strong>
          </p>
          <p className="pwa-wechat-hint">
            建议使用 <strong>Chrome</strong> 或 <strong>Safari</strong> 浏览器
            以获得完整的离线录音与问卷填写体验。
          </p>
          <button
            className="pwa-wechat-dismiss"
            onClick={() => setDismissedWeChat(true)}
          >
            我知道了
          </button>
        </div>
      </div>
    );
  }

  // ── 2. iOS Safari — Add to Home Screen banner ──
  if (isIOS && !dismissedIOS) {
    return (
      <div className="pwa-ios-banner">
        <div className="pwa-ios-content">
          <div className="pwa-ios-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <rect width="24" height="24" rx="6" fill="#1E3A8A" />
              <path
                d="M12 6v12m-6-6h12"
                stroke="#fff"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div className="pwa-ios-text">
            <strong>添加到主屏幕</strong>
            <span className="pwa-ios-sub">
              点击底部「分享」→「添加到主屏幕」，即可离线使用
            </span>
          </div>
          <button
            className="pwa-ios-close"
            onClick={() => setDismissedIOS(true)}
            aria-label="关闭提示"
          >
            ✕
          </button>
        </div>
      </div>
    );
  }

  // ── 3. Android Chrome — floating install button ──
  if (deferredPrompt) {
    return (
      <button
        className="pwa-install-fab"
        onClick={async () => {
          try {
            await deferredPrompt.prompt();
            const { outcome } = await deferredPrompt.userChoice;
            if (outcome === "accepted") {
              setDeferredPrompt(null);
            }
          } catch {
            // user dismissed or browser error — keep button visible
          }
        }}
        aria-label="安装应用到桌面"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path
            d="M10 2v11M6 9l4 4 4-4M3 16h14"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span>安装到桌面</span>
      </button>
    );
  }

  return null;
}
