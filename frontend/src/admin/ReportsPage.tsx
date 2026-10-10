import { useState } from 'react'
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import { api, errorMessage } from '../shared/api'
import { useIsMobile } from '../shared/useIsMobile'
import type { ReportAdmin } from '../shared/types'

type WindowValue = [Dayjs | null, Dayjs | null] | null

interface ReportFormValues {
  title: string
  description?: string
  sort_order?: number
  is_active?: boolean
  window?: WindowValue
}

interface ReportPayload {
  title: string
  description?: string
  sort_order?: number
  is_active?: boolean
  start_at?: string | null
  end_at?: string | null
}

function windowBadge(report: ReportAdmin) {
  const now = dayjs()
  if (report.start_at && now.isBefore(dayjs(report.start_at))) {
    return <Tag>未开始</Tag>
  }
  if (report.end_at && now.isAfter(dayjs(report.end_at))) {
    return <Tag>已结束</Tag>
  }
  return <Tag color="processing">填报中</Tag>
}

function windowText(report: ReportAdmin) {
  const fmt = (value?: string | null) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '')
  if (!report.start_at && !report.end_at) return '不限时间'
  return `${fmt(report.start_at) || '不限'} ~ ${fmt(report.end_at) || '不限'}`
}

export default function ReportsPage() {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const [form] = Form.useForm<ReportFormValues>()
  const [editing, setEditing] = useState<ReportAdmin | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const query = useQuery<ReportAdmin[]>({
    queryKey: ['admin', 'reports'],
    queryFn: async () => (await api.get<ReportAdmin[]>('/api/admin/reports')).data,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['admin', 'reports'] })
    queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] })
  }

  const saveMutation = useMutation({
    mutationFn: async (payload: ReportPayload) => {
      if (editing) {
        return api.patch(`/api/admin/reports/${editing.id}`, payload)
      }
      return api.post('/api/admin/reports', payload)
    },
    onSuccess: async () => {
      message.success(editing ? '报告已更新' : '报告已创建')
      setModalOpen(false)
      setEditing(null)
      form.resetFields()
      await invalidate()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const toggleMutation = useMutation({
    mutationFn: async (report: ReportAdmin) =>
      api.patch(`/api/admin/reports/${report.id}`, { is_active: !report.is_active }),
    onSuccess: async () => {
      message.success('状态已更新')
      await invalidate()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const openCreate = () => {
    setEditing(null)
    form.setFieldsValue({
      title: '',
      description: '',
      sort_order: 0,
      is_active: true,
      window: null,
    })
    setModalOpen(true)
  }

  const openEdit = (report: ReportAdmin) => {
    setEditing(report)
    form.setFieldsValue({
      title: report.title,
      description: report.description ?? '',
      sort_order: report.sort_order,
      is_active: report.is_active,
      window:
        report.start_at || report.end_at
          ? [report.start_at ? dayjs(report.start_at) : null, report.end_at ? dayjs(report.end_at) : null]
          : null,
    })
    setModalOpen(true)
  }

  const submitForm = (values: ReportFormValues) => {
    const [start, end] = values.window ?? [null, null]
    saveMutation.mutate({
      title: values.title,
      description: values.description,
      sort_order: values.sort_order,
      is_active: values.is_active,
      start_at: start ? start.toISOString() : null,
      end_at: end ? end.toISOString() : null,
    })
  }

  const copyLink = async (report: ReportAdmin) => {
    const url = `${window.location.origin}/m/${report.id}`
    try {
      await navigator.clipboard.writeText(url)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = url
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    message.success('客户端填报链接已复制')
  }

  const columns: ColumnsType<ReportAdmin> = [
    {
      title: '报告 ID',
      dataIndex: 'id',
      width: 180,
      fixed: 'left',
      render: (id: string) => (
        <Typography.Text copyable={{ text: id }} style={{ fontSize: 12 }}>
          {id.slice(0, 12)}…
        </Typography.Text>
      ),
    },
    {
      title: '报告标题',
      dataIndex: 'title',
      width: 280,
      ellipsis: true,
      render: (title: string) => <Typography.Text strong>{title}</Typography.Text>,
    },
    {
      title: '填写说明',
      dataIndex: 'description',
      width: 280,
      ellipsis: true,
      responsive: ['xl'],
      render: (value?: string | null) => value || '-',
    },
    {
      title: '填报时间',
      key: 'window',
      width: isMobile ? 150 : 320,
      render: (_, record) => (
        <Typography.Text style={{ fontSize: 12 }}>{windowText(record)}</Typography.Text>
      ),
    },
    {
      title: '填报状态',
      key: 'windowState',
      width: 110,
      render: (_, record) => (record.is_active ? windowBadge(record) : <Tag>已停用</Tag>),
    },
    {
      title: '提交数',
      dataIndex: 'submission_count',
      width: 100,
      render: (count: number) => <Typography.Text strong>{count}</Typography.Text>,
    },
    { title: '排序', dataIndex: 'sort_order', width: 90, responsive: ['lg'] },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: isMobile ? 130 : 260,
      render: (_, record) => (
        <Space size={4} direction={isMobile ? 'vertical' : 'horizontal'}>
          <Button type="link" size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small" onClick={() => toggleMutation.mutate(record)}>
            {record.is_active ? '停用' : '启用'}
          </Button>
          <Button type="link" size="small" onClick={() => copyLink(record)}>
            复制链接
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Card
      className="admin-panel"
      title={
        <Space wrap>
          <Typography.Text strong>报告管理</Typography.Text>
          <Typography.Text type="secondary">共 {query.data?.length ?? 0} 个报告</Typography.Text>
        </Space>
      }
      extra={
        <Tooltip title="创建后可复制客户端填报链接，客户端只能凭该链接进入">
          <Button type="primary" onClick={openCreate}>
            新建报告
          </Button>
        </Tooltip>
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        报告 ID 为 32 位随机字符串；未设置时间段表示长期开放，超出时间段客户端链接将无法填报。
      </Typography.Paragraph>

      <Table<ReportAdmin>
        rowKey="id"
        size={isMobile ? 'small' : 'middle'}
        loading={query.isLoading}
        columns={columns}
        dataSource={query.data ?? []}
        scroll={{ x: 1650 }}
        pagination={false}
      />

      <Modal
        title={editing ? '编辑报告' : '新建报告'}
        open={modalOpen}
        onOk={() => form.submit()}
        confirmLoading={saveMutation.isPending}
        onCancel={() => {
          setModalOpen(false)
          setEditing(null)
        }}
        width={580}
      >
        <Form form={form} layout="vertical" onFinish={submitForm}>
          <Form.Item
            name="title"
            label="报告标题"
            rules={[{ required: true, message: '请输入报告标题' }, { max: 512 }]}
          >
            <Input placeholder="例如：2026 年度专家信息收集" maxLength={512} />
          </Form.Item>
          <Form.Item name="description" label="填写说明（显示在客户端顶部）">
            <Input.TextArea rows={3} maxLength={2000} placeholder="例如：请填写真实的单位与联系方式" />
          </Form.Item>
          <Form.Item
            name="window"
            label="填报时间段（留空表示长期开放）"
            extra="不在时间段内，客户端链接将提示无法填报"
          >
            <DatePicker.RangePicker
              showTime={{ format: 'HH:mm' }}
              format="YYYY-MM-DD HH:mm"
              allowEmpty={[true, true]}
              style={{ width: '100%' }}
              placeholder={['开始时间', '结束时间']}
            />
          </Form.Item>
          <Space size={24} wrap>
            <Form.Item name="sort_order" label="排序" style={{ marginBottom: 0 }}>
              <InputNumber min={0} max={9999} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="is_active" label="启用填报" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Card>
  )
}
