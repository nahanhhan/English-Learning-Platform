import { Button, Slider, Tooltip } from 'antd'
import { Loader2, Volume2, VolumeX } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import {
  getSpeechStatus,
  getSpeechVolume,
  retrySpeaking,
  setSpeechVolume,
  subscribeSpeechStatus,
  subscribeSpeechVolume,
  toggleSpeechMute,
} from '../speak'
import AppIcon from './AppIcon'

export default function VolumeControl() {
  const volume = useSyncExternalStore(subscribeSpeechVolume, getSpeechVolume)
  const speechStatus = useSyncExternalStore(subscribeSpeechStatus, getSpeechStatus)

  return (
    <div className="volume-control" role="group" aria-label="发音音量控制">
      <Tooltip title={volume === 0 ? '取消静音' : '静音'}>
        <button
          type="button"
          className="volume-icon-btn ap-press"
          aria-label={volume === 0 ? '取消发音静音' : '静音发音'}
          onClick={toggleSpeechMute}
        >
          <AppIcon icon={volume === 0 ? VolumeX : Volume2} size={15} />
        </button>
      </Tooltip>
      <span className="volume-label">音量</span>
      <div className="volume-slider-wrap">
        <Slider
          min={0}
          max={100}
          step={5}
          value={volume}
          onChange={setSpeechVolume}
          ariaLabelForHandle="发音音量"
          tooltip={{ formatter: value => `${value}%` }}
        />
      </div>
      <span className="volume-value" aria-live="polite">
        {volume}%
      </span>
      {speechStatus.state === 'loading' && (
        <Tooltip title={speechStatus.message}>
          <span className="speech-loading" aria-label="正在准备自然发音">
            <AppIcon icon={Loader2} size={14} className="ap-spin" />
          </span>
        </Tooltip>
      )}
      {speechStatus.state === 'error' && (
        <Tooltip title={speechStatus.message}>
          <Button
            size="small"
            type="link"
            className="speech-retry"
            onClick={() => retrySpeaking()}
            aria-label={speechStatus.message}
          >
            重试发音
          </Button>
        </Tooltip>
      )}
    </div>
  )
}
