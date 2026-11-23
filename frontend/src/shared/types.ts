export type SubmissionStatus = 'pending' | 'approved' | 'rejected' | 'sent' | 'failed'

export interface ReportPublic {
  id: string
  title: string
  description?: string | null
  start_at?: string | null
  end_at?: string | null
  state?: 'open' | 'not_started' | 'ended'
}

export interface ReportAdmin extends ReportPublic {
  is_active: boolean
  sort_order: number
  created_at: string
  updated_at: string
  submission_count: number
  email_subject?: string | null
  has_email_template?: boolean
  email_template_name?: string | null
  email_template_updated_at?: string | null
  attachment_count?: number
}

export interface ReportAttachment {
  name: string
  size: number
  updated_at?: string | null
}

export interface Submission {
  id: number
  report_id?: string | null
  report_title?: string | null
  organization: string
  position: string
  name: string
  phone: string
  phone_source: string
  email: string
  status: SubmissionStatus
  send_mode?: 'auto' | 'manual'
  needs_manual?: boolean
  person_has_sent?: boolean
  is_processed: boolean
  processed_at?: string | null
  processed_action?: string | null
  ai_flag?: string | null
  ai_score?: number | null
  ai_reason?: string | null
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
