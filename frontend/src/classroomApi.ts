import { api } from './api'

export type Kind = 'all' | 'word' | 'phrase'
export type PracticeSource = 'normal' | 'mistake'
export type VocabularyLibrary = 'classroom' | 'accumulation'
export interface ClassroomGroup {
  id: number; name: string; total: number; mistakes: number
  words: number; phrases: number; word_mistakes: number; phrase_mistakes: number
}
export interface ClassroomEntry {
  id: number; group_id: number; group_name: string; item_type: 'word' | 'phrase'
  english: string; translation: string; source: string
  phonetic_us?: string
  english_definitions?: string[]; english_definition_source?: string
  part_of_speech?: string
  in_mistake_book: boolean; mistake_consec: number; completed: number
  recent_accuracy?: number | null; recent_attempts?: number; last_practiced_at?: string | null
}
export interface PracticeQuestion extends ClassroomEntry {
  option_labels?: string[]; translation_label?: string
  question_id: number; stage: 'choice' | 'spell' | 'done'; options: string[]
  picked: string | null; spell_wrong: boolean; rating: string
}
export interface PracticeRound {
  id: number; version: number; source: PracticeSource; finished: boolean
  total: number; completed: number; correct: number; updated_at: string
  upcoming_speech?: { english: string; translation: string }[]
  current: PracticeQuestion | null
}
export interface ImportRow {
  english: string; translation: string; item_type: 'word' | 'phrase'
  source: string; raw: string; group_id?: number; included: boolean; key: number
}
export const classroom = <T,>(path: string, options?: RequestInit) => api<T>(`/api/classroom${path}`, options)
export const vocabularyApis = {
  classroom,
  accumulation: <T,>(path: string, options?: RequestInit) => api<T>(`/api/accumulation${path}`, options),
}
