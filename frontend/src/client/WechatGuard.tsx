import type { ReactNode } from 'react'

export default function WechatGuard({ children }: { children: ReactNode }) {
  const isWechat = /MicroMessenger/i.test(navigator.userAgent)
  if (!isWechat && !import.meta.env.DEV) {
    return (
      <div className="blocker">
        <h2>请在微信中打开</h2>
        <p>本页面仅支持在微信内置浏览器中访问，请将链接发送到微信后重新打开。</p>
      </div>
    )
  }
  return <>{children}</>
}
