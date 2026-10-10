import WechatGuard from './WechatGuard'

function Home() {
  return (
    <div className="notice-page">
      <div className="notice-card">
        <div className="notice-emoji">🔗</div>
        <div className="notice-title">请使用专用链接打开</div>
        <div className="notice-text">
          本页面不支持选择报告。
          <br />
          请通过管理员提供的报告链接进入填报。
        </div>
      </div>
    </div>
  )
}

export default function ClientHome() {
  return (
    <WechatGuard>
      <Home />
    </WechatGuard>
  )
}
