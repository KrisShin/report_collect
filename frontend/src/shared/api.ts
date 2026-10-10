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

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
    return error.message
  }
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}
