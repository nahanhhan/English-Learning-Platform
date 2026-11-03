import { api } from './api'

export interface ShortQuestion {
  id: string; title: string; topic: string; source: string; sentences: string[]
  completed: boolean; in_review: boolean; streak: number; first_score: number | null; latest_score: number | null
}
export interface ShortResult {
  score: number; overall_comment: string; dimensions: Record<string, number>; improved_version: string
  band?: string; score_reason?: string; rubric_version?: string
  sentence_comments: { sentence_index: number; translation: string; comment: string; suggestion: string; errors: string[]; improvements: string[] }[]
  key_notes: { expr: string; translation: string; note: string; item_type: string }[]
  resolved_points: string[]; remaining_points: string[]
}
export interface ShortAttempt {
  id: number; run_id: string; content: string; is_revision: boolean; status: 'pending' | 'grading' | 'done' | 'failed'
  score: number | null; result: ShortResult | null; profile: Record<string, string>; mock: boolean; error: string; created_at: string
}
export interface ShortRun {
  id: string; question: ShortQuestion; is_review: boolean; attempts: ShortAttempt[]; in_review: boolean; streak: number
  reference: string | null; training_points: string[]
}
export interface ShortStats {
  total: number; completed: number; unseen: number; review: number; first_average: number | null; latest_average: number | null
  topics: string[]; performance: ShortQuestion[]
}
export const shortApi = <T,>(path: string, options?: RequestInit) => api<T>(`/api/short-translation${path}`, options)
export const shortPost = <T,>(path: string, body: unknown) => shortApi<T>(path, { method: 'POST', body: JSON.stringify(body) })
