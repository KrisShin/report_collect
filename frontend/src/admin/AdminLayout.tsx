import { useEffect, useState } from 'react'
import { Button, Form, Input, Layout, Modal, Space, Spin, Typography, message } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Outlet, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../shared/api'
import type { AdminMe } from '../shared/types'

const { Header, Content } = Layout

export default function AdminLayout() {
  const navigate = useNavigate()
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

  return (
    <Layout className="admin-shell">
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingInline: 16 }}>
        <Typography.Text style={{ color: '#fff', fontSize: 16, fontWeight: 600 }}>
          报告收集 · 管理端
        </Typography.Text>
        <Space>
          <Typography.Text style={{ color: 'rgba(255,255,255,.75)' }}>
            {meQuery.data?.display_name ?? meQuery.data?.username}
          </Typography.Text>
          <Button size="small" onClick={() => setPwdOpen(true)}>
            修改密码
          </Button>
          <Button size="small" danger onClick={logout}>
            退出
          </Button>
        </Space>
      </Header>

      <Content className="admin-content">
        <Outlet />
      </Content>

      <Modal title="修改密码" open={pwdOpen} onOk={changePassword} onCancel={() => setPwdOpen(false)}>
        <Form form={pwdForm} layout="vertical">
          <Form.Item name="old_password" label="原密码" rules={[{ required: true, message: '请输入原密码' }]}>
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
