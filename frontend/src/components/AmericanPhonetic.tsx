export default function AmericanPhonetic({ value }: { value?: string }) {
  const phonetic = (value || '').trim().replace(/^[/\[]|[/\]]$/g, '')
  return <span className="american-phonetic" aria-label="美式音标">
    {phonetic ? `美 /${phonetic}/` : '美式音标暂缺'}
  </span>
}
