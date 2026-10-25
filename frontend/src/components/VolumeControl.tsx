import { LoadingOutlined, MutedOutlined, SoundOutlined } from '@ant-design/icons'
import { Button, Slider, Tooltip } from 'antd'
import { useSyncExternalStore } from 'react'
import { getSpeechStatus, getSpeechVolume, retrySpeaking, setSpeechVolume, subscribeSpeechStatus, subscribeSpeechVolume, toggleSpeechMute } from '../speak'

export default function VolumeControl() {
  const volume = useSyncExternalStore(subscribeSpeechVolume, getSpeechVolume)
  const speechStatus = useSyncExternalStore(subscribeSpeechStatus, getSpeechStatus)
  return <div className="volume-control" role="group" aria-label="发音音量控制">
    <Tooltip title={volume === 0 ? '取消静音' : '静音'}>
      <Button type="text" size="small" aria-label={volume === 0 ? '取消发音静音' : '静音发音'}
        icon={volume === 0 ? <MutedOutlined /> : <SoundOutlined />}
        onClick={toggleSpeechMute} />
    </Tooltip>
    <span className="volume-label">音量</span>
    <Slider min={0} max={100} step={5} value={volume} onChange={setSpeechVolume}
      ariaLabelForHandle="发音音量" tooltip={{ formatter: value => `${value}%` }} />
    <span className="volume-value" aria-live="polite">{volume}%</span>
    {speechStatus.state === 'loading' && <Tooltip title={speechStatus.message}>
      <LoadingOutlined aria-label="正在准备自然发音" className="speech-loading" />
    </Tooltip>}
    {speechStatus.state === 'error' && <Tooltip title={speechStatus.message}>
      <Button size="small" type="link" className="speech-retry" onClick={() => retrySpeaking()} aria-label={speechStatus.message}>重试发音</Button>
    </Tooltip>}
  </div>
}
