// 所有词条统一由后端的自然女声生成；失败不切换其他声线。
export type Accent = 'uk' | 'us'

let currentAudio: HTMLAudioElement | null = null
let currentUrl: string | null = null
let currentRequest: AbortController | null = null
let generation = 0
let lastSpeech: { text: string; accent: Accent } | null = null
export type SpeechStatus = { state: 'idle' | 'loading' | 'playing' | 'error'; message: string }
let status: SpeechStatus = { state: 'idle', message: '' }
const statusListeners = new Set<() => void>()
export function getSpeechStatus() { return status }
export function subscribeSpeechStatus(listener: () => void) {
  statusListeners.add(listener)
  return () => { statusListeners.delete(listener) }
}
function setStatus(state: SpeechStatus['state'], message = '') {
  status = { state, message }
  statusListeners.forEach(listener => listener())
}
const VOLUME_KEY = 'english-speech-volume'
const LAST_VOLUME_KEY = 'english-speech-last-volume'
const DEFAULT_VOLUME = 35
const volumeListeners = new Set<() => void>()

function readVolume(key = VOLUME_KEY): number {
  try {
    const saved = window.localStorage.getItem(key)
    if (saved === null || saved.trim() === '') return DEFAULT_VOLUME
    const value = Number(saved)
    return Number.isFinite(value) ? Math.round(Math.max(0, Math.min(100, value))) : DEFAULT_VOLUME
  } catch { return DEFAULT_VOLUME }
}

let volume = readVolume()
let lastNonZeroVolume = volume || readVolume(LAST_VOLUME_KEY) || DEFAULT_VOLUME
export function getSpeechVolume() { return volume }
export function subscribeSpeechVolume(listener: () => void) {
  volumeListeners.add(listener)
  return () => { volumeListeners.delete(listener) }
}

function applyVolume(value: number) {
  volume = value
  if (value > 0) lastNonZeroVolume = value
  if (currentAudio) currentAudio.volume = volume / 100
  if (volume === 0) stopSpeaking()
  volumeListeners.forEach(listener => listener())
}

export function setSpeechVolume(value: number) {
  if (!Number.isFinite(value)) return
  applyVolume(Math.round(Math.max(0, Math.min(100, value))))
  try {
    window.localStorage.setItem(VOLUME_KEY, String(volume))
    if (volume > 0) window.localStorage.setItem(LAST_VOLUME_KEY, String(volume))
  } catch { /* 仍可调节本次音量 */ }
}

export function toggleSpeechMute() { setSpeechVolume(volume === 0 ? lastNonZeroVolume : 0) }

// 同浏览器其他窗口调整音量时同步，避免页面显示与播放音量不一致。
window.addEventListener('storage', event => {
  if (event.key === VOLUME_KEY || event.key === null) applyVolume(readVolume())
  if (event.key === LAST_VOLUME_KEY || event.key === null) lastNonZeroVolume = readVolume(LAST_VOLUME_KEY) || DEFAULT_VOLUME
})

function releaseAudio() {
  if (currentAudio) {
    currentAudio.onended = null
    currentAudio.onerror = null
    try { currentAudio.pause() } catch { /* 已卸载等异常忽略 */ }
    currentAudio = null
  }
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl)
    currentUrl = null
  }
}

/** 取消准备中的请求并停止当前音频，迟到的响应不得开始播放。 */
export function stopSpeaking() {
  generation += 1
  currentRequest?.abort()
  currentRequest = null
  releaseAudio()
  lastSpeech = null
  setStatus('idle')
}

export function retrySpeaking() {
  const previous = lastSpeech
  if (previous) return speak(previous.text, previous.accent)
}

/** 同一题切换答题阶段时不让迟到的自动发音开始；已经开始的发音自然读完。 */
export function cancelPendingSpeech() {
  if (status.state === 'loading') stopSpeaking()
}

export async function speak(text: string, accent: Accent = 'us'): Promise<void> {
  const word = (text || '').trim()
  stopSpeaking()
  if (!word || volume === 0) return
  lastSpeech = { text: word, accent }
  const token = generation
  const controller = new AbortController()
  currentRequest = controller
  let timedOut = false
  const timeout = setTimeout(() => { timedOut = true; controller.abort() }, 35000)
  setStatus('loading', '正在准备自然发音…')
  try {
    const response = await fetch('/api/speech', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: word, accent }), signal: controller.signal,
    })
    if (!response.ok) throw new Error('speech unavailable')
    if (!response.headers.get('content-type')?.startsWith('audio/')) throw new Error('invalid audio')
    const blob = await response.blob()
    if (token !== generation || controller.signal.aborted || volume === 0) return
    clearTimeout(timeout)
    if (!blob.size) throw new Error('empty audio')
    currentUrl = URL.createObjectURL(blob)
    const audio = new Audio(currentUrl)
    currentAudio = audio
    audio.volume = volume / 100
    audio.onended = () => {
      if (currentAudio !== audio) return
      releaseAudio()
      setStatus('idle')
    }
    audio.onerror = () => {
      if (currentAudio !== audio) return
      releaseAudio()
      setStatus('error', '发音暂不可用，点击重试')
    }
    await audio.play()
    if (token === generation && currentAudio === audio) setStatus('playing')
  } catch (error) {
    if (token !== generation || (controller.signal.aborted && !timedOut)) return
    releaseAudio()
    const blocked = error instanceof Error && error.name === 'NotAllowedError'
    setStatus('error', blocked ? '请点击重试播放发音' : '发音暂不可用，点击重试')
  } finally {
    clearTimeout(timeout)
    if (currentRequest === controller) currentRequest = null
  }
}
