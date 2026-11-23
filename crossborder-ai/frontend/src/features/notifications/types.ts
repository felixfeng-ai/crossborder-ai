export interface NotificationItem {
  id: string
  notification_type: string
  title: string
  body: string
  deep_link: string
  work_item_id: string | null
  status: string
  created_at: string
  read_at: string | null
}

export interface NotificationPreferences {
  morning_brief: boolean
  day_closeout: boolean
  needs_action: boolean
  action_failed: boolean
  authorization_expired: boolean
  quiet_start_hour: number | null
  quiet_end_hour: number | null
  timezone: string
}
