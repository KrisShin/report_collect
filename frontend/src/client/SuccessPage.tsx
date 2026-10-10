import { Button, Result } from 'antd-mobile'
import { useNavigate } from 'react-router-dom'

export default function SuccessPage() {
  const navigate = useNavigate()

  return (
    <div className="page-shell">
      <Result
        status="success"
        title="提交成功"
        description="您的信息已提交，等待管理员审核后发送到您的邮箱，请留意查收。"
      />
      <Button block color="primary" fill="outline" onClick={() => navigate('/m', { replace: true })}>
        返回
      </Button>
    </div>
  )
}
