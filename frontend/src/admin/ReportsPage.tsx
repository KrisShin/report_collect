import { useState } from 'react'
import {
  Button,
  Card,
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import { api, errorMessage } from '../shared/api'
import { formatShanghai } from '../shared/datetime'
import { useIsMobile } from '../shared/useIsMobile'
import type { ReportAdmin, ReportAttachment } from '../shared/types'

type WindowValue = [Dayjs | null, Dayjs | null] | null

interface ReportFormValues {
  title: string
  description?: string
  email_subject?: string
  sort_order?: number
  is_active?: boolean
  window?: WindowValue
}

interface ReportPayload {
  title: string
  description?: string
  email_subject?: string | null
  sort_order?: number
  is_active?: boolean
  start_at?: string | null
  end_at?: string | null
}

interface AttachmentResponse {
  items: ReportAttachment[]
  total: number
  uses_legacy: boolean
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
  const fmt = (value?: string | null) => formatShanghai(value)
  if (!report.start_at && !report.end_at) return '不限时间'
  return `${fmt(report.start_at) || '不限'} ~ ${fmt(report.end_at) || '不限'}`
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export default function ReportsPage() {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const [form] = Form.useForm<ReportFormValues>()
  const [editing, setEditing] = useState<ReportAdmin | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [templateFile, setTemplateFile] = useState<File | null>(null)
  const [attachmentFiles, setAttachmentFiles] = useState<File[]>([])

  const query = useQuery<ReportAdmin[]>({
    queryKey: ['admin', 'reports'],
    queryFn: async () => (await api.get<ReportAdmin[]>('/api/admin/reports')).data,
  })

  const attachmentsQuery = useQuery<AttachmentResponse>({
    queryKey: ['admin', 'report-attachments', editing?.id],
    queryFn: async () =>
      (
        await api.get<AttachmentResponse>(
          `/api/admin/reports/${editing!.id}/attachments`,
        )
      ).data,
    enabled: modalOpen && Boolean(editing?.id),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['admin', 'reports'] })
    queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] })
  }

  const invalidateAttachments = (reportId?: string | null) => {
    if (reportId) {
      queryClient.invalidateQueries({
        queryKey: ['admin', 'report-attachments', reportId],
      })
    }
  }

  const toggleMutation = useMutation({
    mutationFn: async (report: ReportAdmin) =>
      api.patch(`/api/admin/reports/${report.id}`, { is_active: !report.is_active }),
    onSuccess: async () => {
      message.success('状态已更新')
      await invalidate()
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const resetAssetState = () => {
    setTemplateFile(null)
    setAttachmentFiles([])
  }

  const closeModal = () => {
    setModalOpen(false)
    setEditing(null)
    resetAssetState()
    form.resetFields()
  }

  const openCreate = () => {
    setEditing(null)
    resetAssetState()
    form.setFieldsValue({
      title: '',
      description: '',
      email_subject: '',
      sort_order: 0,
      is_active: true,
      window: null,
    })
    setModalOpen(true)
  }

  const openEdit = (report: ReportAdmin) => {
    setEditing(report)
    resetAssetState()
    form.setFieldsValue({
      title: report.title,
      description: report.description ?? '',
      email_subject: report.email_subject ?? '',
      sort_order: report.sort_order,
      is_active: report.is_active,
      window:
        report.start_at || report.end_at
          ? [
              report.start_at ? dayjs(report.start_at) : null,
              report.end_at ? dayjs(report.end_at) : null,
            ]
          : null,
    })
    setModalOpen(true)
  }

  const toPayload = (values: ReportFormValues): ReportPayload => {
    const [start, end] = values.window ?? [null, null]
    return {
      title: values.title,
      description: values.description,
      email_subject: values.email_subject?.trim() || null,
      sort_order: values.sort_order,
      is_active: values.is_active,
      start_at: start ? start.toISOString() : null,
      end_at: end ? end.toISOString() : null,
    }
  }

  const applyFileChanges = async (reportId: string) => {
    if (templateFile) {
      const formData = new FormData()
      formData.append('file', templateFile)
      await api.post(`/api/admin/reports/${reportId}/email-template`, formData)
    }
    if (attachmentFiles.length) {
      const formData = new FormData()
      attachmentFiles.forEach((file) => formData.append('files', file))
      await api.post(`/api/admin/reports/${reportId}/attachments`, formData)
    }
  }

  const handleSave = async () => {
    let values: ReportFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }

    setSaving(true)
    let created = false
    let reportId = editing?.id ?? ''
    try {
      const payload = toPayload(values)
      if (editing) {
        await api.patch(`/api/admin/reports/${editing.id}`, payload)
        reportId = editing.id
      } else {
        const response = await api.post<{ id: string }>('/api/admin/reports', payload)
        reportId = response.data.id
        created = true
      }
      await applyFileChanges(reportId)
      message.success(editing ? '报告及邮件设置已更新' : '报告已创建')
      closeModal()
      await invalidate()
      invalidateAttachments(reportId)
    } catch (error) {
      if (created) {
        // 报告已创建，关闭弹窗避免再次点击产生重复报告
        closeModal()
        await invalidate()
        message.error(
          `报告已创建，但文件处理失败：${errorMessage(error)}。请重新打开编辑重试`,
        )
      } else {
        message.error(errorMessage(error))
      }
    } finally {
      setSaving(false)
    }
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

  const downloadTemplate = async () => {
    if (!editing) return
    try {
      const response = await api.get<{ html: string; name?: string | null }>(
        `/api/admin/reports/${editing.id}/email-template`,
      )
      const blob = new Blob([response.data.html], { type: 'text/html;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = response.data.name || 'email-template.html'
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  const deleteTemplate = async () => {
    if (!editing) return
    try {
      await api.delete(`/api/admin/reports/${editing.id}/email-template`)
      message.success('模板已删除，将使用系统默认模板')
      await invalidate()
      invalidateAttachments(editing.id)
      setEditing({ ...editing, has_email_template: false, email_template_name: null })
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  const deleteAttachment = async (name: string) => {
    if (!editing) return
    try {
      await api.delete(
        `/api/admin/reports/${editing.id}/attachments/${encodeURIComponent(name)}`,
      )
      message.success('附件已删除')
      await invalidate()
      invalidateAttachments(editing.id)
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  const importGlobalTemplate = async () => {
    if (!editing) return
    try {
      const response = await api.post<{ name: string; updated_at: string }>(
        `/api/admin/reports/${editing.id}/email-template/import-global`,
      )
      message.success('已导入全局模板；如需主题与正文一致，请填写邮件主题')
      setEditing({
        ...editing,
        has_email_template: true,
        email_template_name: response.data.name,
        email_template_updated_at: response.data.updated_at,
      })
      await invalidate()
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  const importGlobalAttachments = async () => {
    if (!editing) return
    try {
      const response = await api.post<{ imported: string[]; total: number }>(
        `/api/admin/reports/${editing.id}/attachments/import-global`,
      )
      message.success(`已导入 ${response.data.imported.length} 个全局附件`)
      await invalidate()
      invalidateAttachments(editing.id)
    } catch (error) {
      // 没有可导入文件时后端返回 404，用 warning 提示更友好
      message.warning(errorMessage(error))
    }
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
      title: '邮件设置',
      key: 'mail',
      width: 200,
      responsive: ['xl'],
      render: (_, record) => (
        <Space size={4} wrap>
          <Tag color={record.has_email_template ? 'green' : 'default'}>
            {record.has_email_template ? '自定义模板' : '默认模板'}
          </Tag>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {record.attachment_count ? `${record.attachment_count} 个附件` : '无上传附件'}
          </Typography.Text>
        </Space>
      ),
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

  const existingAttachments = attachmentsQuery.data?.items ?? []

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
        scroll={{ x: 1850 }}
        pagination={false}
      />

      <Modal
        title={editing ? '编辑报告' : '新建报告'}
        open={modalOpen}
        onOk={handleSave}
        confirmLoading={saving}
        onCancel={closeModal}
        width={isMobile ? '95%' : 720}
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
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

          <Divider titlePlacement="start">邮件设置</Divider>

          <Form.Item
            name="email_subject"
            label="邮件主题"
            extra="留空时使用【报告分享】+ 报告标题；仅对后续发送的邮件生效"
          >
            <Input
              maxLength={255}
              placeholder="留空使用【报告分享】+ 报告标题"
            />
          </Form.Item>

          <div className="mail-asset-block">
            <div className="mail-asset-label">邮件 HTML 模板</div>
            <Space wrap>
              {editing?.has_email_template ? (
                <>
                  <Tag color="green">自定义模板</Tag>
                  <Typography.Text>
                    {editing.email_template_name || 'email-template.html'}
                  </Typography.Text>
                  {editing.email_template_updated_at && (
                    <Typography.Text type="secondary" className="mail-asset-size">
                      {formatShanghai(editing.email_template_updated_at)}
                    </Typography.Text>
                  )}
                  <Button size="small" onClick={downloadTemplate}>
                    下载
                  </Button>
                  <Popconfirm
                    title="确定删除自定义模板？删除后将使用系统默认模板。"
                    onConfirm={deleteTemplate}
                  >
                    <Button size="small" danger>
                      删除
                    </Button>
                  </Popconfirm>
                </>
              ) : (
                <Typography.Text type="secondary">使用系统默认模板</Typography.Text>
              )}
            </Space>
            <Space wrap className="mail-asset-actions">
              <Upload
                accept=".html,.htm"
                showUploadList={false}
                beforeUpload={(file) => {
                  setTemplateFile(file)
                  return false
                }}
              >
                <Button>{editing?.has_email_template ? '替换模板' : '选择 HTML 模板'}</Button>
              </Upload>
              {editing && !editing.has_email_template && (
                <Button onClick={importGlobalTemplate}>导入全局模板</Button>
              )}
              {templateFile && (
                <>
                  <Typography.Text type="secondary">
                    已选择：{templateFile.name}（保存时上传）
                  </Typography.Text>
                  <Button size="small" type="link" onClick={() => setTemplateFile(null)}>
                    移除
                  </Button>
                </>
              )}
            </Space>
            <div className="mail-asset-hint">
              仅支持 UTF-8 编码的 .html/.htm 文件，最大 512 KB；上传内容按静态 HTML 原样发送。
              导入全局模板会复制一份到本报告，原全局模板保留。
            </div>
          </div>

          <div className="mail-asset-block">
            <div className="mail-asset-label">邮件附件</div>
            {existingAttachments.length > 0 && (
              <div className="mail-asset-list">
                {existingAttachments.map((item) => (
                  <div key={item.name} className="mail-asset-item">
                    <span>{item.name}</span>
                    <span className="mail-asset-size">{formatBytes(item.size)}</span>
                    <Popconfirm
                      title="确定删除该附件？删除后本报告下次发送将不再附带它。"
                      onConfirm={() => deleteAttachment(item.name)}
                    >
                      <Button size="small" type="link" danger>
                        删除
                      </Button>
                    </Popconfirm>
                  </div>
                ))}
              </div>
            )}
            {attachmentFiles.length > 0 && (
              <div className="mail-asset-list">
                {attachmentFiles.map((file, index) => (
                  <div key={`${file.name}-${index}`} className="mail-asset-item">
                    <span>{file.name}</span>
                    <span className="mail-asset-size">{formatBytes(file.size)}</span>
                    <Button
                      size="small"
                      type="link"
                      onClick={() =>
                        setAttachmentFiles((prev) => prev.filter((_, itemIndex) => itemIndex !== index))
                      }
                    >
                      移除
                    </Button>
                  </div>
                ))}
              </div>
            )}
            {existingAttachments.length === 0 && attachmentFiles.length === 0 && (
              <Typography.Text type="secondary">
                未上传报告附件，将使用服务器 mail_attachments/ 中的旧附件
              </Typography.Text>
            )}
            <Space wrap className="mail-asset-actions">
              <Upload
                multiple
                showUploadList={false}
                beforeUpload={(file) => {
                  setAttachmentFiles((prev) => [...prev, file])
                  return false
                }}
              >
                <Button>选择附件（可多选）</Button>
              </Upload>
              {editing && existingAttachments.length === 0 && (
                <Button onClick={importGlobalAttachments}>导入全局附件</Button>
              )}
            </Space>
            <div className="mail-asset-hint">
              同名文件将覆盖；单文件不超过 20 MB；支持 pdf/doc/xlsx/ppt/zip/图片等常用格式。
              导入全局附件会复制一份到本报告，原全局文件保留。
            </div>
          </div>
        </Form>
      </Modal>
    </Card>
  )
}
