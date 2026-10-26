import { Tooltip } from 'antd'

const LABELS: Record<string, string> = {
  'n.': '名词', 'v.': '动词', 'vt.': '及物动词', 'vi.': '不及物动词',
  'adj.': '形容词', 'adv.': '副词', 'prep.': '介词', 'pron.': '代词',
  'conj.': '连词', 'interj.': '感叹词', 'num.': '数词', 'det.': '限定词',
  'art.': '冠词', 'aux.': '助动词', 'modal.': '情态动词',
}

export default function PartOfSpeech({ value }: { value?: string }) {
  const meanings = value?.split(' / ').map(code => `${code} ${LABELS[code] || ''}`).join(' / ')
  return <Tooltip title={meanings || '可在添加或导入词汇时，在释义开头注明 n.、v.、adj. 等词性'}>
    <span className={`part-of-speech${value ? '' : ' part-of-speech-missing'}`} aria-label={`词性：${meanings || '待补充'}`}>
      {value || '词性待补充'}
    </span>
  </Tooltip>
}
