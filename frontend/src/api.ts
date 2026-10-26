// 统一 API 客户端
const BASE = ''

export async function api<T = any>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await resp.json()
  if (!resp.ok) {
    const msg = (data && (data.detail || data.message)) || `请求失败 (${resp.status})`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export const get = <T = any>(path: string) => api<T>(path)
export const post = <T = any>(path: string, body?: any) =>
  api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
export const put = <T = any>(path: string, body?: any) =>
  api<T>(path, { method: 'PUT', body: JSON.stringify(body) })
export const del = <T = any>(path: string) => api<T>(path, { method: 'DELETE' })

// ---------- 类型 ----------

export interface Question {
  id: number
  exam_type: 'cet6' | 'ky2'
  year: number
  month: number
  set_no: number
  q_type: 'translation' | 'writing' | 'small_writing' | 'big_writing'
  title: string
  prompt: string
  source_text: string
  chart_image: string
  chart_display_image?: string
  chart_original_image?: string
  notes: string
}

export interface Submission {
  id: number
  question_id: number | null
  exam_type: string
  q_type: string
  title: string
  prompt: string
  source_text: string
  content: string
  word_count: number
  status: 'pending' | 'grading' | 'done' | 'failed'
  created_at: string
}

export interface TranslationResult {
  score: number
  band: string
  dimensions: { accuracy: number; language: number; fluency: number }
  overall_comment: string
  errors: { fragment: string; issue_type: string; explanation: string; suggestion?: string; correction?: string }[]
  good_points?: string[]
  improved_version: string
  key_notes?: { expr: string; note: string }[]
}

export interface WritingResult {
  score: number
  band: string
  dimensions: { task: number; organization: number; language: number }
  overall_comment: string
  paragraph_comments: { paragraph: number; comment: string }[]
  errors: { fragment: string; issue_type: string; explanation: string; correction?: string; suggestion?: string }[]
  vocab_upgrades: { original: string; upgrade: string; note: string }[]
  structure_advice: string
  polished_version: string
  model_essay: string
}

export interface Grading {
  id: number
  provider: string
  model: string
  mock: boolean
  score: number
  full_score: number
  result: TranslationResult | WritingResult | null
  error: string
  created_at: string
}

export interface StudyCard {
  card_id: number
  status: string
  starred: boolean
  interval: number
  reps: number
  id: number
  headword?: string
  part_of_speech?: string
  phonetic_us?: string
  text?: string
  translation: string
  definition?: string
  note?: string
  book: string
  in_mistake_book?: boolean
  mistake_consec?: number
  options?: string[]
  answer?: string
}

export interface BookProgress {
  book: string
  total_items: number
  cards: number
  new: number
  learning: number
  review: number
  started: number
  mastered: number
  starred: number
  due_now: number
}
