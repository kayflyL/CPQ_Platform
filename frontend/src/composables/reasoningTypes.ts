export type StepStatus = 'pending' | 'running' | 'done' | 'error'

export interface ReasoningStep {
  key: string
  label: string
  status: StepStatus
  payload?: any
  input?: any
  output?: any
  summary?: string
  artifact?: {
    kind: string
    title: string
    data?: any
  }
  substeps?: { kind: string; text: string }[]
}
