export default function SuccessPage() {
  return (
    <div className="success-page">
      <div className="success-card">
        <div className="success-icon">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M4.5 12.5l5 5 10-11"
              stroke="#fff"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="success-title">提交成功</div>
        <div className="success-divider" />
        <div className="success-text">
          您的信息已提交，等待管理员审核后发送到您的邮箱。
          <br />
          请留意查收邮件。
        </div>
        <div className="success-note">
          本页面无需其他操作，可直接关闭。
          <br />
          如需修改信息，请联系报告管理员。
        </div>
      </div>
    </div>
  )
}
