import dayjs, { type Dayjs } from 'dayjs'
import timezone from 'dayjs/plugin/timezone'
import utc from 'dayjs/plugin/utc'

dayjs.extend(utc)
dayjs.extend(timezone)

const DISPLAY_TIMEZONE = 'Asia/Shanghai'
type DateInput = string | number | Date | Dayjs

export function formatShanghai(
  value: DateInput | null | undefined,
  format = 'YYYY-MM-DD HH:mm',
): string {
  if (value === null || value === undefined || value === '') return ''
  return dayjs(value).tz(DISPLAY_TIMEZONE).format(format)
}
