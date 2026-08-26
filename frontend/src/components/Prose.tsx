import type { ReactNode } from 'react'

/** Inline emphasis and code, without pulling in a markdown library.
 *  A coworker answers in prose with the odd bold label and clause id; that is all this
 *  needs to handle. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = []
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g
  let last = 0
  let match: RegExpExecArray | null
  let i = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index))
    const token = match[0]
    const key = `${keyPrefix}-${i++}`
    if (token.startsWith('**')) {
      out.push(
        <strong key={key} className="font-medium text-ink-900">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('`')) {
      out.push(
        <code key={key} className="font-mono text-[12.5px] bg-ink-100 rounded px-1 py-0.5">
          {token.slice(1, -1)}
        </code>,
      )
    } else {
      out.push(
        <em key={key} className="italic">
          {token.slice(1, -1)}
        </em>,
      )
    }
    last = match.index + token.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

/** Renders a coworker's answer: paragraphs, bullet lists and inline emphasis. */
export function Prose({ text, className = '' }: { text: string; className?: string }) {
  const lines = (text ?? '').split('\n')
  const blocks: ReactNode[] = []
  let bullets: string[] = []

  const flush = () => {
    if (!bullets.length) return
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="space-y-1.5 my-2 ml-1">
        {bullets.map((b, i) => (
          <li key={i} className="flex gap-2.5">
            <span className="text-ink-400 shrink-0 mt-[7px] w-1 h-1 rounded-full bg-ink-400" />
            <span>{inline(b, `b${blocks.length}-${i}`)}</span>
          </li>
        ))}
      </ul>,
    )
    bullets = []
  }

  lines.forEach((raw, idx) => {
    const line = raw.trim()
    const bullet = line.match(/^[*\-•]\s+(.*)$/)
    if (bullet) {
      bullets.push(bullet[1])
      return
    }
    flush()
    if (!line) return
    blocks.push(
      <p key={`p-${idx}`} className="mb-2 last:mb-0">
        {inline(line, `p${idx}`)}
      </p>,
    )
  })
  flush()

  return <div className={`leading-relaxed ${className}`}>{blocks}</div>
}
