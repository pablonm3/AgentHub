import { useLayoutEffect, useRef, type KeyboardEventHandler } from 'react'
import { textarea } from './theme'
import { MicButton, type Dictation } from './voice'

interface Props {
  value: string
  onChange: (text: string) => void
  /** From `useDictation`; the caller keeps it to cancel a session and show its error. */
  voice: Dictation
  /** Starting height, in lines of the field's text. */
  minRows: number
  disabled?: boolean
  placeholder?: string
  autoFocus?: boolean
  onKeyDown?: KeyboardEventHandler<HTMLTextAreaElement>
}

/**
 * The field a card's description is written in, in the "Add a card" form and in the card
 * dialog: `minRows` lines high while the text is short, then as tall as its text, at most
 * 60% of the screen, with the microphone beside it.
 */
export default function DescriptionField({
  value,
  onChange,
  voice,
  minRows,
  disabled = false,
  placeholder,
  autoFocus = false,
  onKeyDown,
}: Props) {
  const field = useRef<HTMLTextAreaElement>(null)
  // The value last typed or last scrolled to by the effect below; any other value from props is dictated text.
  const lastSeenValue = useRef(value)

  // The browser keeps the cursor in sight for typed text only. A change that was not typed
  // is a dictated phrase, added at the end: show the end.
  useLayoutEffect(() => {
    const el = field.current
    if (!el || value === lastSeenValue.current) return
    lastSeenValue.current = value
    el.scrollTop = el.scrollHeight
    el.scrollIntoView({ block: 'nearest' })
  }, [value])

  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
      <textarea
        ref={field}
        aria-label="Description"
        rows={minRows}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        autoFocus={autoFocus}
        onChange={(e) => {
          lastSeenValue.current = e.target.value
          onChange(e.target.value)
        }}
        onKeyDown={onKeyDown}
        style={{
          ...textarea,
          flex: '1 1 0',
          minWidth: 0,
          fieldSizing: 'content',
          // `rows` has no effect on a field sized by its content: 20px per line, 22px of padding and border.
          minHeight: minRows * 20 + 22,
          maxHeight: '60vh',
        }}
      />
      <MicButton voice={voice} disabled={disabled} />
    </div>
  )
}
