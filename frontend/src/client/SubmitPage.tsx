import { useEffect, useState } from 'react'
import axios from 'axios'
import { Button, Form, Input, SpinLoading, Toast } from 'antd-mobile'
import { useNavigate, useParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { api, errorMessage, reportDiagnostic } from '../shared/api'
import type { ReportPublic } from '../shared/types'
import WechatGuard from './WechatGuard'

interface FormValues {
  organization: string
  position: string
  name: string
  phone: string
  email: string
}

const PHONE_RE = /^1[3-9]\d{9}$/
const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/

function ReportWindowNotice({ report }: { report: ReportPublic }) {
  const notStarted = report.state === 'not_started'
  const moment = notStarted ? report.start_at : report.end_at

  return (
    <div className="notice-page">
      <div className="notice-card">
        <div className="notice-emoji notice-emoji-gold">{notStarted ? '🕒' : '📮'}</div>
        <div className="notice-title">{notStarted ? '填报尚未开始' : '本次填报已结束'}</div>
        <div className="notice-divider" />
        <div className="notice-text">
          {notStarted
            ? '本次报告收集将于以下时间开放，请届时再打开本链接。'
            : '本次报告收集已于以下时间结束，感谢您的关注与参与。'}
        </div>
        {moment && <div className="notice-time">{dayjs(moment).format('YYYY-MM-DD HH:mm')}</div>}
        <div className="notice-report">{report.title}</div>
      </div>
    </div>
  )
}

function SubmitForm({ reportId }: { reportId: string }) {
  const [form] = Form.useForm()
  const navigate = useNavigate()
  const [report, setReport] = useState<ReportPublic | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [values, setValues] = useState<Partial<FormValues>>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setReport(null)
    setLoadError(null)
    reportDiagnostic('page_open', { message: `report_id=${reportId}` })
    api
      .get<ReportPublic>(`/api/client/reports/${reportId}`)
      .then((response) => setReport(response.data))
      .catch((error) => {
        reportDiagnostic('report_load_error', {
          status: axios.isAxiosError(error) ? error.response?.status : undefined,
          message: errorMessage(error),
          detail: axios.isAxiosError(error) ? error.response?.data : String(error),
        })
        setLoadError(errorMessage(error))
      })
  }, [reportId])

  const canSubmit =
    Boolean(values.organization?.trim()) &&
    Boolean(values.position?.trim()) &&
    Boolean(values.name?.trim()) &&
    PHONE_RE.test(values.phone ?? '') &&
    EMAIL_RE.test(values.email ?? '')

  const onFinish = async (formValues: FormValues) => {
    setSubmitting(true)
    const payload = { ...formValues, report_id: reportId }
    try {
      const response = await api.post('/api/client/submissions', payload)
      reportDiagnostic('submit_ok', { message: 'created', detail: response.data })
      navigate('/m/success', { replace: true })
    } catch (error) {
      reportDiagnostic('submit_error', {
        status: axios.isAxiosError(error) ? error.response?.status : undefined,
        message: errorMessage(error),
        detail: axios.isAxiosError(error) ? error.response?.data : String(error),
        payload,
      })
      Toast.show({ content: errorMessage(error), duration: 3000 })
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) {
    return (
      <div className="notice-page">
        <div className="notice-card">
          <div className="notice-emoji">⚠️</div>
          <div className="notice-title">无法填报</div>
          <div className="notice-text">{loadError}</div>
        </div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="page-loading">
        <SpinLoading color="primary" />
      </div>
    )
  }

  if (report.state && report.state !== 'open') {
    return <ReportWindowNotice report={report} />
  }

  return (
    <div className="client-page">
      <div className="client-hero">
        <div className="client-hero-badge">Tsinghua EIRI · Report</div>
        <div className="client-hero-title">{report.title}</div>
        <div className="client-hero-desc">
          {report.description || '请填写以下信息，提交后由管理员审核并发送到您的邮箱。'}
        </div>
      </div>

      <div className="client-card">
        <div className="client-card-hint">以下均为必填项</div>
        <Form
          form={form}
          className="rc-form"
          layout="vertical"
          onValuesChange={(_, allValues) => setValues(allValues as Partial<FormValues>)}
          onFinish={onFinish}
        >
          <Form.Item
            name="organization"
            label="单位"
            rules={[
              { required: true, message: '请输入单位' },
              { max: 512, message: '单位不能超过 512 个字符' },
            ]}
          >
            <Input placeholder="请输入单位全称" maxLength={512} clearable />
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
            <Input placeholder="请输入 11 位手机号" type="tel" maxLength={11} clearable />
          </Form.Item>

          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },
              { pattern: EMAIL_RE, message: '请输入有效的邮箱地址' },
            ]}
          >
            <Input placeholder="请输入常用邮箱" type="email" clearable />
          </Form.Item>
        </Form>
      </div>

      <div className="client-footer">
        <Button
          block
          className="rc-primary-btn"
          loading={submitting}
          disabled={!canSubmit || submitting}
          onClick={() => form.submit()}
        >
          提交信息
        </Button>
        <div className="client-footer-tip">
          信息仅用于本次报告收集，请确保填写真实有效
          <br />
          审核结果将通过邮件发送，请留意收件箱与垃圾邮件文件夹
        </div>
      </div>
    </div>
  )
}

export default function SubmitPage() {
  const params = useParams()
  const reportId = params.reportId ?? ''

  if (!/^[0-9a-f]{32}$/.test(reportId)) {
    return (
      <div className="notice-page">
        <div className="notice-card">
          <div className="notice-emoji">🔗</div>
          <div className="notice-title">链接无效</div>
          <div className="notice-text">报告链接不正确，请使用管理员提供的填报链接。</div>
        </div>
      </div>
    )
  }

  return (
    <WechatGuard>
      <SubmitForm reportId={reportId} />
    </WechatGuard>
  )
}
