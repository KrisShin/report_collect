export type SubmissionStatus = 'pending' | 'approved' | 'rejected' | 'sent' | 'failed'

export interface Submission {
  id: number
  organization: string
  position: string
  name: string
  phone: string
  phone_source: string
  email: string
  status: SubmissionStatus
  review_note?: string | null
  submitted_at: string
  mail_sent_at?: string | null
  feishu_status?: string | null
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface AdminMe {
  id: number
  username: string
  display_name: string
  must_change_password: boolean
}
