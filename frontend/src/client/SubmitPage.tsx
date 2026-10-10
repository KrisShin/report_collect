import { useEffect, useState } from 'react'
import { Button, Form, Input, Toast } from 'antd-mobile'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../shared/api'
import WechatGuard from './WechatGuard'

interface FormValues {
  organization: string
  position: string
  name: string
  phone: string
  email: string
}

const PHONE_RE = /^1[3-9]\d{9}$/
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function SubmitForm() {
  const [form] = Form.useForm()
  const navigate = useNavigate()
  const location = useLocation()
  const [values, setValues] = useState<Partial<FormValues>>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (params.get('wx') === '1') return

    let cancelled = false
    api
      .get<{ url: string }>('/api/client/wechat/authorize-url')
      .then(({ data }) => {
        if (!cancelled) window.location.replace(data.url)
      })
      .catch(() => {
        /* 微信未配置时忽略，允许手动填写 */
      })
    return () => {
      cancelled = true
    }
  }, [location.search])

  const canSubmit =
    Boolean(values.organization?.trim()) &&
    Boolean(values.position?.trim()) &&
    Boolean(values.name?.trim()) &&
    PHONE_RE.test(values.phone ?? '') &&
    EMAIL_RE.test(values.email ?? '')

  const onFinish = async (formValues: FormValues) => {
    setSubmitting(true)
    try {
      await api.post('/api/client/submissions', formValues)
      navigate('/m/success', { replace: true })
    } catch (error) {
      Toast.show({ content: errorMessage(error) })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-shell">
      <div className="page-title">报告信息收集</div>
      <div className="page-subtitle">请填写以下信息，提交后由管理员审核并发送到您的邮箱。</div>

      <Form
        form={form}
        layout="vertical"
        mode="card"
        onValuesChange={(_, allValues) => setValues(allValues as Partial<FormValues>)}
        onFinish={onFinish}
        footer={
          <Button
            block
            color="primary"
            size="large"
            type="submit"
            loading={submitting}
            disabled={!canSubmit}
          >
            提交
          </Button>
        }
      >
        <Form.Item
          name="organization"
          label="单位"
          rules={[
            { required: true, message: '请输入单位' },
            { max: 512, message: '单位不能超过 512 个字符' },
          ]}
        >
          <Input placeholder="请输入单位" maxLength={512} clearable />
        </Form.Item>

        <Form.Item
          name="position"
          label="职务"
          rules={[
            { required: true, message: '请输入职务' },
            { max: 512, message: '职务不能超过 512 个字符' },
          ]}
        >
          <Input placeholder="请输入职务" maxLength={512} clearable />
        </Form.Item>

        <Form.Item
          name="name"
          label="姓名"
          rules={[
            { required: true, message: '请输入姓名' },
            { max: 32, message: '姓名不能超过 32 个字符' },
          ]}
        >
          <Input placeholder="请输入姓名" maxLength={32} clearable />
        </Form.Item>

        <Form.Item
          name="phone"
          label="电话"
          rules={[
            { required: true, message: '请输入手机号' },
            { pattern: PHONE_RE, message: '请输入有效的 11 位手机号' },
          ]}
        >
          <Input placeholder="请输入手机号" type="tel" maxLength={11} clearable />
        </Form.Item>

        <Form.Item
          name="email"
          label="邮箱"
          rules={[
            { required: true, message: '请输入邮箱' },
            { pattern: EMAIL_RE, message: '请输入有效的邮箱地址' },
          ]}
        >
          <Input placeholder="请输入邮箱" type="email" clearable />
        </Form.Item>
      </Form>
    </div>
  )
}

export default function SubmitPage() {
  return (
    <WechatGuard>
      <SubmitForm />
    </WechatGuard>
  )
}
