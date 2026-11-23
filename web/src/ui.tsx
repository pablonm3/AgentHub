import {
  Component,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Task, TaskStatus, User } from './api'
import { formatDuration, formatTokens, taskElapsed } from './lib/format'
import { parts } from './lib/mentions'
import { serverNow } from './store'
import { color, dark, font, input, statusLook } from './theme'

// ---- time ----------------------------------------------------------------------------------

/** The server's current time, re-read every `intervalMs` while `active`. */
export function useNow(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(serverNow)
  useEffect(() => {
    if (!active) return
    setNow(serverNow())
    const timer = window.setInterval(() => setNow(serverNow()), intervalMs)
    return () => window.clearInterval(timer)
  }, [active, intervalMs])
  return active ? now : serverNow()
}

/** The working timer of a task: it advances only while the task is running. */
export function Timer({ task, style }: { task: Pick<Task, 'status' | 'running_ms' | 'running_since'>; style?: CSSProperties }) {
  const running = task.status === 'running' && task.running_since !== null
  const now = useNow(running)
  return (
    <span
      title="Working time"
      style={{ fontFamily: font.mono, fontSize: 12, lineHeight: '16px', fontVariantNumeric: 'tabular-nums', ...style }}
    >
      {formatDuration(taskElapsed(task, now))}
    </span>
  )
}

/** The two token counts of a task or a ticket, labelled "session" and "harness". */
export function TokenCounts({
  session,
  harness,
  darkMode = false,
  style,
}: {
  session: number
  harness: number
  darkMode?: boolean
  style?: CSSProperties
}) {
  const label = { color: darkMode ? dark.dim : color.muted, fontFamily: font.sans, fontWeight: 400 }
  return (
    <span
      style={{
        display: 'inline-flex',
        gap: 10,
        fontFamily: font.mono,
        fontSize: 12,
        lineHeight: '16px',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      <span title="Tokens of the AI user's own session">
        {formatTokens(session)} <span style={label}>session</span>
      </span>
      <span title="Tokens of the harness runs the task started">
        {formatTokens(harness)} <span style={label}>harness</span>
      </span>
    </span>
  )
}

// ---- people and status ---------------------------------------------------------------------

export function Avatar({
  user,
  size = 26,
  ring = color.surface,
  overlap = 0,
  style,
}: {
  user: Pick<User, 'name' | 'initials' | 'color'> | undefined
  size?: number
  ring?: string
  overlap?: number
  style?: CSSProperties
}) {
  if (!user) return null
  return (
    <span
      title={user.name}
      aria-label={user.name}
      style={{
        flex: `0 0 ${size}px`,
        width: size,
        height: size,
        marginLeft: overlap ? -overlap : 0,
        borderRadius: '50%',
        border: ring === 'none' ? 0 : `2px solid ${ring}`,
        background: user.color,
        color: '#FFFFFF',
        fontSize: size >= 30 ? 11 : 10,
        lineHeight: '12px',
        fontWeight: 600,
        display: 'grid',
        placeItems: 'center',
        ...style,
      }}
    >
      {user.initials}
    </span>
  )
}

export function StatusPill({ status, small = false }: { status: TaskStatus; small?: boolean }) {
  const look = statusLook[status] ?? statusLook.done
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: small ? 5 : 6,
        padding: small ? '2px 8px' : '4px 10px',
        borderRadius: 999,
        background: look.bg,
        color: look.fg,
        fontSize: small ? 11 : 12,
        lineHeight: '16px',
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: small ? 6 : 7,
          height: small ? 6 : 7,
          borderRadius: '50%',
          background: look.dot,
          animation: status === 'running' ? 'wb-pulse 1.4s ease-in-out infinite' : 'none',
        }}
      />
      {look.label}
    </span>
  )
}

// ---- controls ------------------------------------------------------------------------------

type ButtonKind = 'primary' | 'ghost' | 'outline' | 'dark' | 'darkOutline' | 'danger'

const buttonLooks: Record<ButtonKind, CSSProperties> = {
  primary: { border: 0, background: color.accent, color: '#FFFFFF' },
  ghost: { border: 0, background: 'transparent', color: color.ink2 },
  outline: { border: `1px solid ${color.lineStrong}`, background: color.surface, color: color.ink },
  dark: { border: 0, background: color.ink, color: '#FFFFFF' },
  darkOutline: { border: `1px solid ${dark.button}`, background: 'transparent', color: '#E6E9EF' },
  danger: { border: `1px solid #C2453A`, background: color.surface, color: '#9B1C12' },
}

export function Button({
  kind = 'outline',
  compact = false,
  style,
  className,
  type = 'button',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { kind?: ButtonKind; compact?: boolean }) {
  const hover = kind === 'darkOutline' ? 'wb-ghost-dark' : kind === 'primary' || kind === 'dark' ? '' : 'wb-ghost'
  return (
    <button
      type={type}
      className={[hover, className].filter(Boolean).join(' ') || undefined}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        minHeight: compact ? 32 : 40,
        padding: compact ? '0 10px' : '0 16px',
        borderRadius: 9,
        fontSize: 13,
        fontWeight: 600,
        whiteSpace: 'nowrap',
        ...buttonLooks[kind],
        ...style,
      }}
      {...rest}
    />
  )
}

export interface Option {
  value: string
  label: string
  disabled?: boolean
}

export function Select({
  value,
  onChange,
  options,
  ariaLabel,
  id,
  disabled,
  darkMode = false,
  placeholder,
  style,
}: {
  value: string
  onChange: (value: string) => void
  options: Option[]
  ariaLabel?: string
  id?: string
  disabled?: boolean
  darkMode?: boolean
  /** Shown first and selected while `value` is empty; it cannot be picked. */
  placeholder?: string
  style?: CSSProperties
}) {
  return (
    <select
      id={id}
      aria-label={ariaLabel}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      style={{
        ...input,
        minHeight: 40,
        padding: '0 10px',
        ...(darkMode ? { background: dark.header, color: dark.bright, border: `1px solid ${dark.button}` } : {}),
        ...style,
      }}
    >
      {placeholder !== undefined && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} style={{ fontSize: 13, fontWeight: 600, color: color.ink }}>
      {children}
    </label>
  )
}

/** The dashed box shown where a list is empty; `compact` inside a board column. */
export function EmptyState({ children, compact = false }: { children: ReactNode; compact?: boolean }) {
  return (
    <p
      style={{
        margin: 0,
        padding: compact ? '18px 12px' : '28px 16px',
        border: `1px dashed ${color.lineStrong}`,
        borderRadius: compact ? 10 : 12,
        color: color.muted,
        fontSize: compact ? 13 : undefined,
        textAlign: 'center',
      }}
    >
      {children}
    </p>
  )
}

/** A form's error line, announced to screen readers. */
export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p role="alert" style={{ margin: 0, color: color.errorInk, fontSize: 13 }}>
      {children}
    </p>
  )
}

/** A title shown as text with a pencil button; editing saves on Enter or blur. */
export function EditableTitle({
  value,
  muted = false,
  onSave,
  ariaLabel = 'Edit title',
  darkMode = false,
  textStyle,
}: {
  value: string
  muted?: boolean
  onSave: (next: string) => Promise<void>
  ariaLabel?: string
  darkMode?: boolean
  textStyle?: CSSProperties
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [busy, setBusy] = useState(false)
  const done = useRef(false)

  const start = () => {
    setDraft(value)
    done.current = false
    setEditing(true)
  }
  const finish = async (save: boolean) => {
    if (done.current) return
    done.current = true
    const next = draft.trim()
    if (!save || !next || next === value) {
      setEditing(false)
      return
    }
    setBusy(true)
    try {
      await onSave(next)
      setEditing(false)
    } catch {
      // The caller reported the error; keep the field open so the text is not lost.
      done.current = false
    } finally {
      setBusy(false)
    }
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    e.stopPropagation()
    if (e.key === 'Enter') {
      e.preventDefault()
      void finish(true)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      void finish(false)
    }
  }

  if (editing) {
    return (
      <input
        type="text"
        aria-label={ariaLabel}
        value={draft}
        autoFocus
        disabled={busy}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={() => void finish(true)}
        onClick={(e) => e.stopPropagation()}
        style={{
          ...input,
          minHeight: 36,
          fontSize: 15,
          fontWeight: 600,
          ...(darkMode ? { background: dark.footer, color: dark.bright, border: `1px solid ${dark.button}` } : {}),
        }}
      />
    )
  }
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0, maxWidth: '100%' }}>
      <span
        style={{
          minWidth: 0,
          overflowWrap: 'anywhere',
          color: muted ? (darkMode ? dark.sub : color.muted) : undefined,
          fontStyle: muted ? 'italic' : undefined,
          ...textStyle,
        }}
      >
        {value}
      </span>
      <button
        type="button"
        aria-label={ariaLabel}
        title={ariaLabel}
        className={darkMode ? 'wb-ghost-dark' : 'wb-ghost'}
        onClick={(e) => {
          e.stopPropagation()
          start()
        }}
        onKeyDown={(e) => e.stopPropagation()}
        style={{
          flex: '0 0 28px',
          width: 28,
          height: 28,
          display: 'grid',
          placeItems: 'center',
          border: 0,
          borderRadius: 7,
          background: 'transparent',
          color: darkMode ? dark.sub : color.muted,
        }}
      >
        <PencilIcon />
      </button>
    </span>
  )
}

// ---- dialogs -------------------------------------------------------------------------------

/** The prototype's modal: a backdrop that closes on click and a dialog that closes on Escape. */
export function Dialog({
  label,
  onClose,
  zIndex = 40,
  maxWidth = 880,
  darkMode = false,
  children,
}: {
  label: string
  onClose: () => void
  zIndex?: number
  maxWidth?: number
  darkMode?: boolean
  children: ReactNode
}) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // Take focus for Escape, unless a field inside already took it with autoFocus.
    if (box.current && !box.current.contains(document.activeElement)) box.current.focus()
  }, [])
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        padding: '32px 16px',
        overflowY: 'auto',
      }}
    >
      <button
        type="button"
        aria-label={`Close ${label}`}
        tabIndex={-1}
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          width: '100%',
          height: '100%',
          padding: 0,
          border: 0,
          background: darkMode ? 'rgba(15, 18, 24, 0.6)' : color.backdrop,
          cursor: 'default',
        }}
      />
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className={darkMode ? 'wb-dark' : undefined}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.stopPropagation()
            onClose()
          }
        }}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth,
          display: 'flex',
          flexDirection: 'column',
          outline: 'none',
          overflow: darkMode ? 'hidden' : undefined,
          background: darkMode ? dark.bg : color.surface,
          color: darkMode ? dark.text : color.ink,
          borderRadius: 14,
          boxShadow: darkMode ? '0 24px 64px rgba(15, 18, 24, 0.45)' : '0 24px 64px rgba(15, 18, 24, 0.28)',
        }}
      >
        {children}
      </div>
    </div>
  )
}

export function CloseButton({ label, onClick, darkMode = false }: { label: string; onClick: () => void; darkMode?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={darkMode ? 'wb-ghost-dark' : 'wb-ghost'}
      onClick={onClick}
      style={{
        width: 44,
        height: 44,
        display: 'grid',
        placeItems: 'center',
        border: 0,
        borderRadius: 9,
        background: 'transparent',
        color: darkMode ? '#E6E9EF' : color.ink2,
      }}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
        <path d="M4 4l8 8M12 4l-8 8" />
      </svg>
    </button>
  )
}

// ---- markdown ------------------------------------------------------------------------------

// A minimal view of the HTML tree react-markdown hands to rehype plugins.
interface HtmlNode {
  type: string
  tagName?: string
  value?: string
  properties?: Record<string, unknown>
  children?: HtmlNode[]
}

const NO_MENTIONS_INSIDE = new Set(['a', 'code', 'pre'])

function highlightMentions(node: HtmlNode, handles: string[]): void {
  if (!node.children) return
  if (node.type === 'element' && node.tagName && NO_MENTIONS_INSIDE.has(node.tagName)) return
  const children: HtmlNode[] = []
  for (const child of node.children) {
    if (child.type === 'text' && typeof child.value === 'string' && child.value.includes('@')) {
      for (const part of parts(child.value, handles)) {
        children.push(
          part.mention
            ? { type: 'element', tagName: 'span', properties: { className: ['ah-mention'] }, children: [{ type: 'text', value: part.text }] }
            : { type: 'text', value: part.text },
        )
      }
    } else {
      highlightMentions(child, handles)
      children.push(child)
    }
  }
  node.children = children
}

function rehypeMentions(options: { handles: string[] }) {
  return (tree: HtmlNode) => highlightMentions(tree, options.handles)
}

const markdownComponents: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
}

/** Markdown with clickable links (opening in a new tab) and highlighted @mentions. */
export function Markdown({ text, handles = [], style }: { text: string; handles?: string[]; style?: CSSProperties }) {
  return (
    <div className="ah-md" style={style}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeMentions, { handles }]]}
        components={markdownComponents}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

// ---- icons ---------------------------------------------------------------------------------

export function BoardIcon({ filled = false }: { filled?: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill={filled ? '#FFFFFF' : 'none'}
      stroke={filled ? 'none' : 'currentColor'}
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="2" y="2.5" width="3" height="11" rx="1" />
      <rect x="6.5" y="2.5" width="3" height="7" rx="1" />
      <rect x="11" y="2.5" width="3" height="9" rx="1" />
    </svg>
  )
}

export function TerminalIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="1.5" y="2.5" width="13" height="11" rx="2" />
      <path d="M4.5 6.5l2 1.75-2 1.75" />
      <path d="M8.5 10.5h3" />
    </svg>
  )
}

export function BellIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 7a4 4 0 0 1 8 0v3l1.5 2h-11L4 10z" />
      <path d="M6.5 14h3" />
    </svg>
  )
}

export function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="8" cy="8" r="2.2" />
      <path d="M8 1.8v1.6M8 12.6v1.6M1.8 8h1.6M12.6 8h1.6M3.6 3.6l1.1 1.1M11.3 11.3l1.1 1.1M3.6 12.4l1.1-1.1M11.3 4.7l1.1-1.1" />
    </svg>
  )
}

export function CommentIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 3.5h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7.5L4.5 14v-2.5H3a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z" />
    </svg>
  )
}

export function ChevronIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke={color.muted} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 3.5l4.5 4.5L6 12.5" />
    </svg>
  )
}

export function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      <path d="M8 3.5v9M3.5 8h9" />
    </svg>
  )
}

function PencilIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.5 2.5l3 3L6 13H3v-3z" />
    </svg>
  )
}

// ---- errors --------------------------------------------------------------------------------

/** Keeps one view's render error from blanking the whole page. */
export class ErrorBoundary extends Component<
  { fallback: (error: Error, reset: () => void) => ReactNode; children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  reset = () => this.setState({ error: null })

  render() {
    return this.state.error ? this.props.fallback(this.state.error, this.reset) : this.props.children
  }
}
