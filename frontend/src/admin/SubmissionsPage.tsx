import { useMemo, useState } from 'react'
import {
  Button,
  Card,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { FilterValue, SorterResult } from 'antd/es/table/interface'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { api, errorMessage } from '../shared/api'
import type { PageResult, Submission, SubmissionStatus } from '../shared/types'

const STATUS_META: Record<SubmissionStatus, { text: string; color: string }> = {
  pending: { text: '待审核', color: 'gold' },
  approved: { text: '已通过', color: 'blue' },
  rejected: { text: '已驳回', color: 'red' },
  sent: { text: '已发送', color: 'green' },
  failed: { text: '发送失败', color: 'volcano' },
}

interface Filters {
  organization?: string
  position?: string
  name?: string
  phone?: string
  email?: string
  status?: string
  keyword?: string
}

export default function SubmissionsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState<Filters>({})
  const [sortBy, setSortBy] = useState('submitted_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  const params = useMemo(
    () => ({ page, page_size: pageSize, sort_by: sortBy, sort_order: sortOrder, ...filters }),
    [page, pageSize, sortBy, sortOrder, filters],
  )

  const query = useQuery<PageResult<Submission>>({
    queryKey: ['admin', 'submissions', params],
    queryFn: async () => (await api.get<PageResult<Submission>>('/api/admin/submissions', { params })).data,
  })

  const reviewMutation = useMutation({
    mutationFn: async ({ id, status }: { id: number; status: 'approved' | 'rejected' }) =>
      api.patch(`/api/admin/submissions/${id}/review`, { status }),
    onSuccess: async () => {
      message.success('操作成功')
      await queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] })
    },
    onError: (error) => message.error(errorMessage(error)),
  })

  const doExport = async () => {
    if (!selectedIds.length) return message.warning('请先选择记录')
    try {
      const response = await api.post('/api/admin/submissions/export', { ids: selectedIds }, { responseType: 'blob' })
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = `报告收集_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  const doSendMail = async () => {
    if (!selectedIds.length) return message.warning('请先选择记录')
    try {
      const response = await api.post('/api/admin/submissions/send-mail', { ids: selectedIds })
      message.success(`已发送 ${response.data.count} 条记录`)
      await queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] })
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  const doCopyEmails = async () => {
    if (!selectedIds.length) return message.warning('请先选择记录')
    try {
      const response = await api.post<{ emails: string; count: number }>(
        '/api/admin/submissions/copy-emails',
        { ids: selectedIds },
      )
      const text = response.data.emails
      try {
        await navigator.clipboard.writeText(text)
      } catch {
        const textarea = document.createElement('textarea')
        textarea.value = text
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        textarea.remove()
      }
      message.success(`已复制 ${response.data.count} 个邮箱`)
    } catch (error) {
      message.error(errorMessage(error))
    }
  }

  const columns: ColumnsType<Submission> = [
    { title: 'ID', dataIndex: 'id', sorter: true, width: 80 },
    { title: '单位', dataIndex: 'organization', sorter: true, width: 220, ellipsis: true },
    { title: '职务', dataIndex: 'position', sorter: true, width: 140, ellipsis: true },
    { title: '姓名', dataIndex: 'name', sorter: true, width: 100 },
    { title: '电话', dataIndex: 'phone', sorter: true, width: 130 },
    { title: '邮箱', dataIndex: 'email', sorter: true, width: 200, ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      sorter: true,
      width: 100,
      render: (status: SubmissionStatus) => {
        const meta = STATUS_META[status] ?? { text: status, color: 'default' }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '提交时间',
      dataIndex: 'submitted_at',
      sorter: true,
      width: 170,
      render: (value: string) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 140,
      render: (_, record) => (
        <Space>
          <Popconfirm
            title="确定通过该记录？"
            onConfirm={() => reviewMutation.mutate({ id: record.id, status: 'approved' })}
          >
            <Button type="link" size="small">
              通过
            </Button>
          </Popconfirm>
          <Popconfirm
            title="确定驳回该记录？"
            onConfirm={() => reviewMutation.mutate({ id: record.id, status: 'rejected' })}
          >
            <Button type="link" size="small" danger>
              驳回
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const handleTableChange = (
    pagination: TablePaginationConfig,
    _filters: Record<string, FilterValue | null>,
    sorter: SorterResult<Submission> | SorterResult<Submission>[],
  ) => {
    setPage(pagination.current ?? 1)
    setPageSize(pagination.pageSize ?? 20)
    const single = Array.isArray(sorter) ? sorter[0] : sorter
    if (single?.field && single?.order) {
      setSortBy(String(single.field))
      setSortOrder(single.order === 'ascend' ? 'asc' : 'desc')
    }
  }

  const updateFilter = (key: keyof Filters, value: string) => {
    setPage(1)
    setFilters((prev) => ({ ...prev, [key]: value || undefined }))
  }

  return (
    <Card
      title={
        <Space wrap>
          <Typography.Text strong>提交记录</Typography.Text>
          <Typography.Text type="secondary">共 {query.data?.total ?? 0} 条</Typography.Text>
        </Space>
      }
      extra={
        <Typography.Text type="secondary">已选 {selectedIds.length} 条</Typography.Text>
      }
    >
      <Space wrap style={{ marginBottom: 12 }}>
        <Input allowClear placeholder="关键词" style={{ width: 180 }} onChange={(e) => updateFilter('keyword', e.target.value)} />
        <Input allowClear placeholder="单位" style={{ width: 160 }} onChange={(e) => updateFilter('organization', e.target.value)} />
        <Input allowClear placeholder="职务" style={{ width: 130 }} onChange={(e) => updateFilter('position', e.target.value)} />
        <Input allowClear placeholder="姓名" style={{ width: 110 }} onChange={(e) => updateFilter('name', e.target.value)} />
        <Input allowClear placeholder="电话" style={{ width: 140 }} onChange={(e) => updateFilter('phone', e.target.value)} />
        <Input allowClear placeholder="邮箱" style={{ width: 180 }} onChange={(e) => updateFilter('email', e.target.value)} />
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 120 }}
          options={Object.entries(STATUS_META).map(([value, meta]) => ({ value, label: meta.text }))}
          onChange={(value?: string) => updateFilter('status', value ?? '')}
        />
      </Space>

      <div className="admin-toolbar">
        <Button onClick={doExport}>一键导出</Button>
        <Button type="primary" onClick={doSendMail}>
          一键发送邮件
        </Button>
        <Button onClick={doCopyEmails}>复制选中邮箱</Button>
      </div>

      <Table<Submission>
        rowKey="id"
        size="small"
        loading={query.isLoading}
        columns={columns}
        dataSource={query.data?.items ?? []}
        scroll={{ x: 1300 }}
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) => setSelectedIds(keys as number[]),
        }}
        pagination={{
          current: page,
          pageSize,
          total: query.data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
        }}
        onChange={handleTableChange}
      />
    </Card>
  )
}
