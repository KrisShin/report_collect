import { useState } from 'react'
import { Button, Card, Form, Input, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../shared/api'

export default function LoginPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      await api.post('/api/admin/auth/login', values)
      message.success('登录成功')
      navigate('/admin', { replace: true })
    } catch (error) {
      message.error(errorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-shell" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Card style={{ width: 360, margin: 16 }}>
        <Typography.Title level={4} style={{ textAlign: 'center', marginBottom: 24 }}>
          报告收集 · 管理端
        </Typography.Title>
        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item name="username" label="账号" rules={[{ required: true, message: '请输入账号' }]}>
            <Input size="large" autoComplete="username" placeholder="请输入账号" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password size="large" autoComplete="current-password" placeholder="请输入密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block loading={loading}>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  )
}
