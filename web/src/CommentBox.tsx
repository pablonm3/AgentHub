import { useId, useMemo, useRef, useState } from 'react'
import { errorMessage } from './api'
import { mentionedHandles, TRAILING_MENTION, withMention } from './lib/mentions'
import { useAppState } from './store'
import { color, textarea } from './theme'
import { Avatar, Button, ErrorText } from './ui'
import { MicButton, useDictation } from './voice'

/**
 * The comment field used by the ticket dialog and by each Activity entry: a textarea, "Tag
 * someone" chips for the four users that insert `@Handle `, and a Post button.
 */
export default function CommentBox({
  label = 'Add a comment',
  hideLabel = false,
  placeholder = 'Write a comment. Type @ to tag someone.',
  rows = 3,
  onSubmit,
}: {
  label?: string
  hideLabel?: boolean
  placeholder?: string
  rows?: number
  /** Posts the text; a rejection keeps the text and shows the error under the box. */
  onSubmit: (body: string) => Promise<void>
}) {
  const { boot } = useAppState()
  const users = boot?.users ?? []
  const id = useId()
  const field = useRef<HTMLTextAreaElement>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const voice = useDictation(setDraft)

  const handles = useMemo(() => users.map((u) => u.handle), [users])
  const mentioned = mentionedHandles(draft, handles)

  // While a handle is being typed after "@", only the chips that match it are offered.
  const typed = TRAILING_MENTION.exec(draft)
  const query = typed ? typed[2].toLowerCase() : ''
  const matching = users.filter((u) => u.handle.toLowerCase().startsWith(query))
  const chips = query && matching.length ? matching : users

  const insertMention = (handle: string) => {
    setDraft(withMention(draft, handle))
    field.current?.focus()
  }

  const submit = async () => {
    const body = draft.trim()
    if (!body || busy) return
    voice.cancel()
    setBusy(true)
    setError(null)
    try {
      await onSubmit(body)
      setDraft('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <label
        htmlFor={id}
        style={
          hideLabel
            ? { position: 'absolute', width: 1, height: 1, overflow: 'hidden', clipPath: 'inset(50%)' }
            : { fontSize: 13, fontWeight: 600 }
        }
      >
        {label}
      </label>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <textarea
          id={id}
          ref={field}
          rows={rows}
          value={draft}
          placeholder={placeholder}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              void submit()
            }
          }}
          style={{ ...textarea, minHeight: rows * 20 + 22, flex: '1 1 0', minWidth: 0 }}
        />
        <MicButton voice={voice} disabled={busy} />
      </div>
      {voice.error && <ErrorText>{voice.error}</ErrorText>}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
        <span style={{ marginRight: 2, color: color.muted, fontSize: 13 }}>Tag someone</span>
        {chips.map((u) => {
          const on = mentioned.includes(u.handle)
          return (
            <button
              key={u.id}
              type="button"
              className="wb-ghost"
              aria-pressed={on}
              onClick={() => insertMention(u.handle)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                minHeight: 36,
                padding: '0 12px 0 6px',
                border: `1px solid ${on ? color.accent : color.line}`,
                borderRadius: 999,
                background: on ? color.accentSoft : color.surface,
                color: on ? color.accentInk : color.ink,
                fontSize: 13,
                fontWeight: on ? 600 : 500,
              }}
            >
              <Avatar user={u} size={24} ring="none" />@{u.handle}
            </button>
          )
        })}
        <Button kind="primary" onClick={() => void submit()} disabled={busy || !draft.trim()} style={{ marginLeft: 'auto' }}>
          {busy ? 'Posting…' : 'Post'}
        </Button>
      </div>
      {error && (
        <ErrorText>{error}</ErrorText>
      )}
    </div>
  )
}
