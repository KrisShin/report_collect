import { useMemo, useState } from 'react'
import {
  Button,
  Card,
  Drawer,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { FilterValue, SorterResult } from 'antd/es/table/interface'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { api, errorMessage } from '../shared/api'
import { useIsMobile } from '../shared/useIsMobile'
import type { PageResult, ReportAdmin, Submission, SubmissionStatus } from '../shared/types'

const STATUS_META: Record<SubmissionStatus, { text: string; color: string }> = {
  pending: { text: '待审核', color: 'gold' },
  approved: { text: '已通过', color: 'blue' },
  rejected: { text: '已驳回', color: 'red' },
  sent: { text: '已发送', color: 'green' },
  failed: { text: '发送失败', color: 'volcano' },
}

const AI_META: Record<string, { text: string; color: string }> = {
  ok: { text: '正常', color: 'green' },
  suspicious: { text: '可疑', color: 'red' },
  error: { text: '判定失败', color: 'orange' },
  skipped: { text: '未判定', color: 'default' },
}

interface Filters {
  report_id?: string
  processed?: string
  ai_flag?: string
  status?: string
  keyword?: string
  organization?: string
  position?: string
  name?: string
  phone?: string
  email?: string
}

export default function SubmissionsPage() {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState<Filters>({})
  const [sortBy, setSortBy] = useState('submitted_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [filterOpen, setFilterOpen] = useState(false)

  const params = useMemo(
    () => ({ page, page_size: pageSize, sort_by: sortBy, sort_order: sortOrder, ...filters }),
    [page, pageSize, sortBy, sortOrder, filters],
  )

  const query = useQuery<PageResult<Submission>>({
    queryKey: ['admin', 'submissions', params],
    queryFn: async () =>
      (await api.get<PageResult<Submission>>('/api/admin/submissions', { params })).data,
  })

  const statsQuery = useQuery({
    queryKey: ['admin', 'submissions', 'stats'],
    queryFn: async () => {
      const base = { page: 1, page_size: 1 }
      const [all, unprocessed, suspicious] = await Promise.all([
        api.get<PageResult<Submission>>('/api/admin/submissions', { params: base }),
        api.get<PageResult<Submission>>('/api/admin/submissions', {
          params: { ...base, processed: false },
        }),
        api.get<PageResult<Submission>>('/api/admin/submissions', {
          params: { ...base, ai_flag: 'suspicious' },
        }),
      ])
      return {
        total: all.data.total,
        unprocessed: unprocessed.data.total,
        suspicious: suspicious.data.total,
      }
    },
  })

  const reportsQuery = useQuery<ReportAdmin[]>({
    queryKey: ['admin', 'reports'],
    queryFn: async () => (await api.get<ReportAdmin[]>('/api/admin/reports')).data,
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
      const response = await api.post(
        '/api/admin/submissions/export',
        { ids: selectedIds },
        { responseType: 'blob' },
      )
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
      message.success(
        `已提交发送任务（${response.data.count} 条），发送完成后会自动标记为已处理`,
      )
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['admin', 'submissions'] })
      }, 4000)
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
    { title: 'ID', dataIndex: 'id', sorter: true, width: 90, fixed: 'left' },
    {
      title: '报告',
      dataIndex: 'report_title',
      width: 220,
      ellipsis: true,
      render: (value?: string | null) => value || '未关联',
    },
    { title: '单位', dataIndex: 'organization', sorter: true, width: 300, ellipsis: true },
    { title: '职务', dataIndex: 'position', sorter: true, width: 180, ellipsis: true },
    { title: '姓名', dataIndex: 'name', sorter: true, width: 120 },
    { title: '电话', dataIndex: 'phone', sorter: true, width: 150 },
    { title: '邮箱', dataIndex: 'email', sorter: true, width: 260, ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      sorter: true,
      width: 110,
      render: (status: SubmissionStatus) => {
        const meta = STATUS_META[status] ?? { text: status, color: 'default' }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '处理状态',
      dataIndex: 'is_processed',
      width: 110,
      render: (value: boolean) =>
        value ? <Tag color="green">已处理</Tag> : <Tag>未处理</Tag>,
    },
    {
      title: 'AI 标记',
      dataIndex: 'ai_flag',
      width: 130,
      render: (flag?: string | null, record?: Submission) => {
        if (!flag) return '-'
        const meta = AI_META[flag] ?? { text: flag, color: 'default' }
        return (
          <Tooltip title={record?.ai_reason ?? '无判定理由'}>
            <Tag color={meta.color}>{meta.text}</Tag>
          </Tooltip>
        )
      },
    },
    {
      title: '提交时间',
      dataIndex: 'submitted_at',
      sorter: true,
      width: 180,
      render: (value: string) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 160,
      render: (_, record) => (
        <Space size={4}>
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

  const updateFilter = (key: keyof Filters, value: string | number | boolean) => {
    setPage(1)
    setFilters((prev) => ({
      ...prev,
      [key]: value === '' || value === undefined ? undefined : value,
    }))
  }

  const clearFilters = () => {
    setPage(1)
    setFilters({})
  }

  const filterControls = (
    <>
      <Select
        allowClear
        placeholder="报告"
        style={{ width: isMobile ? '100%' : 220 }}
        value={filters.report_id}
        options={(reportsQuery.data ?? []).map((report) => ({
          value: report.id,
          label: report.title,
        }))}
        onChange={(value?: string) => updateFilter('report_id', value ?? '')}
      />
      <Input
        allowClear
        placeholder="关键词（姓名/单位/电话/邮箱）"
        style={{ width: isMobile ? '100%' : 240 }}
        onChange={(e) => updateFilter('keyword', e.target.value)}
      />
      <Input
        allowClear
        placeholder="单位"
        style={{ width: isMobile ? '100%' : 180 }}
        onChange={(e) => updateFilter('organization', e.target.value)}
      />
      <Input
        allowClear
        placeholder="职务"
        style={{ width: isMobile ? '100%' : 150 }}
        onChange={(e) => updateFilter('position', e.target.value)}
      />
      <Input
        allowClear
        placeholder="姓名"
        style={{ width: isMobile ? '100%' : 130 }}
        onChange={(e) => updateFilter('name', e.target.value)}
      />
      <Input
        allowClear
        placeholder="电话"
        style={{ width: isMobile ? '100%' : 150 }}
        onChange={(e) => updateFilter('phone', e.target.value)}
      />
      <Input
        allowClear
        placeholder="邮箱"
        style={{ width: isMobile ? '100%' : 200 }}
        onChange={(e) => updateFilter('email', e.target.value)}
      />
      <Select
        allowClear
        placeholder="状态"
        style={{ width: isMobile ? '100%' : 130 }}
        value={filters.status}
        options={Object.entries(STATUS_META).map(([value, meta]) => ({
          value,
          label: meta.text,
        }))}
        onChange={(value?: string) => updateFilter('status', value ?? '')}
      />
      <Select
        allowClear
        placeholder="处理状态"
        style={{ width: isMobile ? '100%' : 140 }}
        value={filters.processed}
        options={[
          { value: 'false', label: '未处理' },
          { value: 'true', label: '已处理' },
        ]}
        onChange={(value?: string) => updateFilter('processed', value ?? '')}
      />
      <Select
        allowClear
        placeholder="AI 标记"
        style={{ width: isMobile ? '100%' : 140 }}
        value={filters.ai_flag}
        options={Object.entries(AI_META).map(([value, meta]) => ({ value, label: meta.text }))}
        onChange={(value?: string) => updateFilter('ai_flag', value ?? '')}
      />
      {isMobile ? (
        <Button block onClick={clearFilters}>
          清空筛选
        </Button>
      ) : (
        <Button onClick={clearFilters}>清空筛选</Button>
      )}
    </>
  )

  return (
    <>
      <div className="stat-row">
        <div className="stat-card">
          <div className="stat-label">提交总数</div>
          <div className="stat-value">{statsQuery.data?.total ?? '-'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">未处理</div>
          <div className="stat-value">{statsQuery.data?.unprocessed ?? '-'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">AI 可疑</div>
          <div className="stat-value">{statsQuery.data?.suspicious ?? '-'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">已选记录</div>
          <div className="stat-value">{selectedIds.length}</div>
        </div>
      </div>

      <Card
        className="admin-panel"
        title={
          <Space wrap>
            <Typography.Text strong>提交记录</Typography.Text>
            <Typography.Text type="secondary">共 {query.data?.total ?? 0} 条</Typography.Text>
          </Space>
        }
      >
        {!isMobile && <div className="admin-filter-bar">{filterControls}</div>}

        <div className="admin-toolbar">
          {isMobile && <Button onClick={() => setFilterOpen(true)}>筛选</Button>}
          <Button onClick={doExport}>一键导出</Button>
          <Button type="primary" onClick={doSendMail}>
            一键发送邮件
          </Button>
          <Button onClick={doCopyEmails}>复制邮箱</Button>
        </div>

        <Table<Submission>
          rowKey="id"
          size={isMobile ? 'small' : 'middle'}
          loading={query.isLoading}
          columns={columns}
          dataSource={query.data?.items ?? []}
          scroll={{ x: 2100 }}
          rowSelection={{
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys as number[]),
          }}
          pagination={{
            current: page,
            pageSize,
            total: query.data?.total ?? 0,
            showSizeChanger: !isMobile,
            showTotal: (total) => `共 ${total} 条`,
          }}
          onChange={handleTableChange}
        />
      </Card>

      <Drawer
        title="筛选条件"
        placement="right"
        width="86%"
        open={filterOpen}
        onClose={() => setFilterOpen(false)}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          {filterControls}
        </Space>
      </Drawer>
    </>
  )
}
