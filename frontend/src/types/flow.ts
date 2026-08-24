export interface ProcessNodeDef {
  key: string
  label: string
  title?: string
  subtitle?: string
  state: 'done' | 'current' | 'pending'
  statusLabel: string
}
