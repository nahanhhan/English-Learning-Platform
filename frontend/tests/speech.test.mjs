import assert from 'node:assert/strict'
import { beforeEach, test } from 'node:test'

const saved = new Map()
const audios = []
const requests = []
const revoked = []
let fallbackCalls = 0
let respond
let play
let urlIndex = 0
globalThis.window = {
  localStorage: { getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value) },
  addEventListener() {},
  speechSynthesis: { speak() { fallbackCalls++ }, cancel() { fallbackCalls++ } },
}
globalThis.Audio = class {
  constructor(url) { this.src = url; this.volume = 1; audios.push(this) }
  play() { return play(this) }
  pause() { this.paused = true }
}
URL.createObjectURL = () => `blob:audio-${++urlIndex}`
URL.revokeObjectURL = url => revoked.push(url)
globalThis.fetch = (url, options) => {
  requests.push({ url, ...options })
  return respond(url, options)
}
const audioResponse = () => new Response(new Uint8Array([255, 243, 0, 0]), { headers: { 'Content-Type': 'audio/mpeg' } })
const speech = await import('../src/speak.ts')
const initialVolume = speech.getSpeechVolume()

beforeEach(() => {
  speech.stopSpeaking()
  speech.setSpeechVolume(35)
  requests.length = 0; audios.length = 0; revoked.length = 0
  fallbackCalls = 0
  respond = async () => audioResponse()
  play = () => Promise.resolve()
})

test('统一后端接口与音量；正在播放的音量可实时修改并保存', async () => {
  assert.equal(initialVolume, 35)
  await speech.speak('have / get a shot at (doing) sth')
  assert.equal(requests[0].url, '/api/speech')
  assert.deepEqual(JSON.parse(requests[0].body), { text: 'have / get a shot at (doing) sth', accent: 'us' })
  assert.equal(audios.at(-1).volume, .35)
  speech.setSpeechVolume(20)
  assert.equal(audios.at(-1).volume, .2)
  assert.equal(saved.get('english-speech-volume'), '20')
  assert.equal(speech.getSpeechStatus().state, 'playing')
})

test('新发音取消上一请求，迟到响应不得播放', async () => {
  let completeFirst
  respond = () => new Promise(resolve => { completeFirst = resolve })
  const first = speech.speak('first')
  respond = async () => audioResponse()
  await speech.speak('second')
  assert.equal(requests[0].signal.aborted, true)
  completeFirst(audioResponse())
  await first
  assert.equal(audios.length, 1)
  assert.equal(JSON.parse(requests[1].body).text, 'second')
})

test('停止和静音取消未完成发音，静音时不请求音频', async () => {
  let finish
  respond = () => new Promise(resolve => { finish = resolve })
  const pending = speech.speak('pending')
  speech.setSpeechVolume(0)
  assert.equal(requests[0].signal.aborted, true)
  finish(audioResponse())
  await pending
  assert.equal(audios.length, 0)
  await speech.speak('silent')
  assert.equal(requests.length, 1)
  assert.equal(speech.getSpeechStatus().state, 'idle')
})

test('静音停止当前播放并释放地址，取消静音不自动补播', async () => {
  await speech.speak('hello')
  const previous = audios[0]
  speech.toggleSpeechMute()
  assert.equal(previous.paused, true)
  assert.deepEqual(revoked, [previous.src])
  speech.toggleSpeechMute()
  assert.equal(speech.getSpeechVolume(), 35)
  assert.equal(audios.length, 1)
})

test('失败只保留重试，不降级到其他声音', async () => {
  respond = async () => new Response('{"detail":"offline"}', { status: 503 })
  await speech.speak('stand sb up', 'uk')
  assert.equal(speech.getSpeechStatus().state, 'error')
  assert.equal(fallbackCalls, 0)
  assert.equal(audios.length, 0)
  respond = async () => audioResponse()
  await speech.retrySpeaking()
  assert.deepEqual(JSON.parse(requests[1].body), { text: 'stand sb up', accent: 'uk' })
  assert.equal(speech.getSpeechStatus().state, 'playing')
})

test('被打断的音频错误不会影响新音频或触发系统语音', async () => {
  await speech.speak('first')
  const first = audios[0]
  const oldError = first.onerror
  await speech.speak('second')
  oldError()
  assert.equal(speech.getSpeechStatus().state, 'playing')
  assert.equal(first.paused, true)
  assert.equal(fallbackCalls, 0)
})

test('播放完成和播放失败均释放临时音频地址', async () => {
  await speech.speak('complete')
  audios[0].onended()
  assert.equal(speech.getSpeechStatus().state, 'idle')
  assert.deepEqual(revoked, [audios[0].src])
  await speech.speak('error')
  audios[1].onerror()
  assert.equal(speech.getSpeechStatus().state, 'error')
  assert.equal(revoked.length, 2)
})

test('浏览器自动播放限制显示手动重试，不切换声线', async () => {
  play = async () => { throw new DOMException('blocked', 'NotAllowedError') }
  await speech.speak('hello')
  assert.match(speech.getSpeechStatus().message, /点击重试/)
  assert.equal(revoked.length, 1)
  assert.equal(fallbackCalls, 0)
})

test('答题阶段切换取消迟到发音，但不截断已经开始的同一词条', async () => {
  let finish
  respond = () => new Promise(resolve => { finish = resolve })
  const pending = speech.speak('pending')
  speech.cancelPendingSpeech()
  finish(audioResponse())
  await pending
  assert.equal(audios.length, 0)
  respond = async () => audioResponse()
  await speech.speak('already playing')
  speech.cancelPendingSpeech()
  assert.equal(audios[0].paused, undefined)
  assert.equal(speech.getSpeechStatus().state, 'playing')
})

test('音量边界、订阅与存储不可用时仍能调节', () => {
  let changes = 0
  const unsubscribe = speech.subscribeSpeechVolume(() => changes++)
  speech.setSpeechVolume(500)
  assert.equal(speech.getSpeechVolume(), 100)
  speech.setSpeechVolume(-1)
  assert.equal(speech.getSpeechVolume(), 0)
  speech.setSpeechVolume(NaN)
  assert.equal(changes, 2)
  unsubscribe()
  const original = window.localStorage.setItem
  window.localStorage.setItem = () => { throw new Error('unavailable') }
  speech.setSpeechVolume(40)
  assert.equal(speech.getSpeechVolume(), 40)
  window.localStorage.setItem = original
})

test('重载后取消静音恢复之前非零音量', async () => {
  saved.set('english-speech-volume', '0')
  saved.set('english-speech-last-volume', '15')
  const reloaded = await import('../src/speak.ts?restore-muted')
  reloaded.toggleSpeechMute()
  assert.equal(reloaded.getSpeechVolume(), 15)
})
