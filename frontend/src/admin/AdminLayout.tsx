import { useEffect, useState } from 'react'
import { Button, Form, Input, Layout, Modal, Space, Spin, Tooltip, message } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../shared/api'
import type { AdminMe } from '../shared/types'

const { Content } = Layout

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const [pwdOpen, setPwdOpen] = useState(false)
  const [pwdForm] = Form.useForm()

  const meQuery = useQuery<AdminMe>({
    queryKey: ['admin', 'me'],
    queryFn: async () => (await api.get<AdminMe>('/api/admin/auth/me')).data,
    retry: false,
  })

  useEffect(() => {
    if (meQuery.isError) navigate('/admin/login', { replace: true })
  }, [meQuery.isError, navigate])

  const logout = async () => {
    await api.post('/api/admin/auth/logout')
    queryClient.clear()
    navigate('/admin/login', { replace: true })
  }

  const changePassword = async () => {
    const values = await pwdForm.validateFields()
    try {
      await api.post('/api/admin/auth/change-password', values)
      message.success('密码修改成功')
      setPwdOpen(false)
      pwdForm.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['admin', 'me'] })
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  if (meQuery.isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 120 }}>
        <Spin size="large" />
      </div>
    )
  }

  const onSubmissions = location.pathname === '/admin' || location.pathname === '/admin/'
  const onReports = location.pathname.startsWith('/admin/reports')

  return (
    <Layout className="admin-shell">
      <div className="admin-header">
        <div className="admin-brand">
          <div className="admin-brand-mark">E</div>
          <div>
            <div className="admin-brand-title">报告收集系统</div>
            <div className="admin-brand-sub">TSINGHUA EIRI</div>
          </div>
        </div>
        <Space size={8} wrap>
          <span className="admin-user">
            {meQuery.data?.display_name ?? meQuery.data?.username}
          </span>
          <Tooltip title="修改登录密码">
            <Button size="small" ghost onClick={() => setPwdOpen(true)}>
              修改密码
            </Button>
          </Tooltip>
          <Button size="small" danger onClick={logout}>
            退出
          </Button>
        </Space>
      </div>

      <div className="admin-nav">
        <Button
          className="admin-nav-pill"
          type={onSubmissions ? 'primary' : 'default'}
          onClick={() => navigate('/admin')}
        >
          提交记录
        </Button>
        <Button
          className="admin-nav-pill"
          type={onReports ? 'primary' : 'default'}
          onClick={() => navigate('/admin/reports')}
        >
          报告管理
        </Button>
      </div>

      <Content className="admin-content">
        <Outlet />
      </Content>

      <Modal title="修改密码" open={pwdOpen} onOk={changePassword} onCancel={() => setPwdOpen(false)}>
        <Form form={pwdForm} layout="vertical">
          <Form.Item
            name="old_password"
            label="原密码"
            rules={[{ required: true, message: '请输入原密码' }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 10, message: '新密码至少 10 位' },
            ]}
          >
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  )
}
