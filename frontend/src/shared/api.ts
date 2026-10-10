import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  withCredentials: true,
  timeout: 30000,
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const onAdminRoute = window.location.pathname.startsWith('/admin')
    const onLoginPage = window.location.pathname.startsWith('/admin/login')
    if (status === 401 && onAdminRoute && !onLoginPage) {
      window.location.replace('/admin/login')
    }
    return Promise.reject(error)
  },
)

const FIELD_LABELS: Record<string, string> = {
  report_id: '报告',
  organization: '单位',
  position: '职务',
  name: '姓名',
  phone: '电话',
  email: '邮箱',
}

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) {
      const item = detail[0] as { loc?: unknown[]; msg?: string }
      const field = Array.isArray(item.loc) ? String(item.loc[item.loc.length - 1]) : ''
      const label = FIELD_LABELS[field]
      const msg = String(item.msg).replace(/^Value error,\s*/, '')
      return label ? `${label}：${msg}` : msg
    }
    return error.message
  }
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

export function reportDiagnostic(event: string, detail?: Record<string, unknown>) {
  return api
    .post('/api/client/diagnostic', {
      event,
      url: window.location.href,
      ua: navigator.userAgent,
      ...detail,
    })
    .catch(() => undefined)
}
