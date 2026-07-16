export interface L6Record {
  id: number
  model?: string
  chassis?: string
  drive_bays?: string
  psu?: string
  motherboard?: string
  price?: number
  note?: string
  date?: string
  match_score?: number
  matched_dims?: number
  total_dims?: number
  match_type?: string
  config_ids?: string
  chassis_types?: string
  sort_order?: number
}
