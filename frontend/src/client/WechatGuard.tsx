import type { ReactNode } from 'react'

/**
 * 仅允许微信内置浏览器访问（与后端 require_wechat_browser 双重校验）。
 * 本地调试若需绕过，可在浏览器 DevTools 里把 UA 覆盖为微信 UA。
 */
export default function WechatGuard({ children }: { children: ReactNode }) {
  const isWechat = /MicroMessenger/i.test(navigator.userAgent)
  if (!isWechat) {
    return (
      <div className="notice-page">
        <div className="notice-card">
          <div className="notice-emoji">💬</div>
          <div className="notice-title">请在微信内打开</div>
          <div className="notice-text">
            本页面仅支持在微信内置浏览器中访问。
            <br />
            请将链接发送到微信后重新打开。
          </div>
        </div>
      </div>
    )
  }
  return <>{children}</>
}
