import { useState, type CSSProperties } from 'react'
import { api, errorMessage, type ChatEvent, type Task, type TaskDetail, type TaskLink, type TaskStatus, type User } from './api'
import { formatRelative, formatTokens } from './lib/format'
import { statusLabel } from './lib/taskStatus'
import {
  applyTaskDetail,
  closeTask,
  findUser,
  loadTasks,
  notifyOnFailure,
  openTask,
  refresh,
  runInBackground,
  serverNow,
  useAppState,
  useOpenTask,
  userName,
  viewTicketOf,
} from './store'
import { dark, font } from './theme'
import { Avatar, Button, CloseButton, Dialog, EditableTitle, Markdown, Select, TaskStatusPill, Timer, TokenCounts } from './ui'
import { MicButton, useDictation } from './voice'

/** One task's chat, opened from the Tasks page or from a ticket's Tasks block. */
export default function TaskDialog() {
  const s = useAppState()
  const { id, detail, item } = useOpenTask()
  const task: Task | undefined = detail ?? item
  if (id === null || !s.boot) return null
  const boot = s.boot

  if (!task) {
    return (
      <Dialog label="Task" onClose={closeTask} zIndex={50} maxWidth={1000} darkMode>
        <div style={{ display: 'flex', alignItems: 'center', padding: '12px 12px 12px 20px', background: dark.header }}>
          <span style={{ color: dark.sub }}>Loading the task…</span>
          <span style={{ marginLeft: 'auto' }}>
            <CloseButton label="Close task" onClick={closeTask} darkMode />
          </span>
        </div>
      </Dialog>
    )
  }

  const user = findUser(boot.users, task.ai_user_id)
  const archived = task.status === 'archived'
  const handles = boot.users.map((u) => u.handle)

  const act = (run: () => Promise<TaskDetail>) =>
    notifyOnFailure(async () => {
      applyTaskDetail(await run())
      refresh('tasks')
    })

  return (
    <Dialog label={task.display_title} onClose={closeTask} zIndex={50} maxWidth={1000} darkMode>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          padding: '12px 12px 12px 20px',
          background: dark.header,
          borderBottom: `1px solid ${dark.line}`,
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px 10px' }}>
          <TaskStatusPill task={task} />
          <span style={{ fontFamily: font.mono, fontSize: 12, lineHeight: '16px', color: dark.sub, overflowWrap: 'anywhere' }}>
            {[task.ticket_key ?? 'No ticket', user?.name ?? task.ai_user_id].join(' · ')}
          </span>
          <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            {task.ticket_id !== null && (
              <Button kind="darkOutline" onClick={() => viewTicketOf(task)}>
                View ticket
              </Button>
            )}
            <CloseButton label="Close task" onClick={closeTask} darkMode />
          </span>
        </div>
        <h2 style={{ margin: 0, color: '#FFFFFF', fontFamily: font.display, fontSize: 19, lineHeight: '26px', fontWeight: 600 }}>
          {archived ? (
            <span>{task.display_title}</span>
          ) : (
            <EditableTitle
              value={task.display_title}
              muted={task.title === null}
              darkMode
              ariaLabel="Edit task title"
              onSave={(title) => act(() => api.updateTask(task.id, { title }))}
            />
          )}
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px 16px', fontSize: 13 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Avatar user={user} size={22} ring="none" />
            {user?.name ?? task.ai_user_id}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: dark.sub }}>
            Model
            <Select
              ariaLabel="Model"
              darkMode
              value={task.model}
              disabled={archived}
              onChange={(model) => runInBackground(act(() => api.updateTask(task.id, { model })))}
              options={boot.models.map((m) => ({ value: m, label: m }))}
              style={{ width: 'auto', minHeight: 32, fontSize: 13 }}
            />
          </span>
          <Timer task={task} style={{ color: dark.bright, fontSize: 13 }} />
          <TokenCounts session={task.session_tokens} harness={task.harness_tokens} darkMode style={{ color: dark.bright }} />
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            {task.status === 'running' && (
              <Button kind="darkOutline" compact onClick={() => runInBackground(act(() => api.stopTask(task.id)))}>
                Stop
              </Button>
            )}
            {task.status === 'done' && (
              <Button kind="darkOutline" compact onClick={() => runInBackground(act(() => api.archiveTask(task.id)))}>
                Archive
              </Button>
            )}
          </span>
        </div>
        {task.status_reason && (
          <p
            role="status"
            style={{
              margin: 0,
              padding: '6px 10px',
              borderRadius: 8,
              border: `1px solid ${dark.ask}`,
              color: dark.ask,
              fontSize: 13,
              lineHeight: '18px',
              overflowWrap: 'anywhere',
            }}
          >
            {task.status_reason}
          </p>
        )}
        {(task.harness_runs ?? []).length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px', fontFamily: font.mono, fontSize: 12, color: dark.sub }}>
            <span style={{ fontFamily: font.sans }}>Harness runs</span>
            {(task.harness_runs ?? []).map((r) => (
              <span key={r.run_id}>
                {r.run_id} · {r.status}
                {r.pending_kind ? ` · waiting at ${r.pending_kind}` : ''} · {formatTokens(r.tokens)} tokens
              </span>
            ))}
          </div>
        )}
        <TaskLinks task={task} />
      </div>
      <Chat task={task} events={detail?.events ?? null} user={user} handles={handles} />
      <MessageBox task={task} />
    </Dialog>
  )
}

/** The parent this task answers to and the child tasks it created; each opens that task. */
function TaskLinks({ task }: { task: Task }) {
  const children = task.children ?? []
  if (!task.parent && children.length === 0) return null
  const link = (t: TaskLink, withPill: boolean) => (
    <button
      key={t.id}
      type="button"
      onClick={() => openTask(t.id)}
      aria-label={`Open ${userName(t.ai_user_id)}'s task ${t.display_title}, ${statusLabel(t, userName)}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        minHeight: 28,
        padding: '2px 8px',
        border: `1px solid ${dark.line}`,
        borderRadius: 8,
        background: 'transparent',
        color: dark.cmd,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {withPill && <TaskStatusPill task={t} small />}
      {userName(t.ai_user_id)} · {t.display_title}
    </button>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, color: dark.sub }}>
      {task.parent && (
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 10px' }}>
          <span>Child of</span>
          {link(task.parent, false)}
        </div>
      )}
      {children.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 10px' }}>
          <span>Child tasks</span>
          {children.map((child) => link(child, true))}
        </div>
      )}
    </div>
  )
}

const CHAT_HINT: Record<TaskStatus, { text: string; color: string; blink: boolean }> = {
  running: { text: 'working', color: dark.dim, blink: true },
  waiting_on_user: { text: 'waiting for your reply', color: dark.ask, blink: false },
  done: { text: 'done · send a message to continue', color: dark.dim, blink: false },
  archived: { text: 'archived · the chat stays readable', color: dark.dim, blink: false },
}

function Chat({
  task,
  events,
  user,
  handles,
}: {
  task: Task
  events: ChatEvent[] | null
  user: User | undefined
  handles: string[]
}) {
  const now = serverNow()
  const hint =
    task.status === 'waiting_on_user' && task.waiting_on
      ? { ...CHAT_HINT.waiting_on_user, text: `waiting for ${userName(task.waiting_on.ai_user_id)}` }
      : CHAT_HINT[task.status]
  return (
    // column-reverse keeps the view pinned to the newest message.
    <div
      style={{
        height: '54vh',
        minHeight: 260,
        display: 'flex',
        flexDirection: 'column-reverse',
        overflowY: 'auto',
        padding: '16px 20px',
        fontSize: 14,
        lineHeight: '21px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {events === null && <div style={{ color: dark.dim, fontFamily: font.mono, fontSize: 13 }}>Loading the chat…</div>}
        {events !== null && events.length === 0 && (
          <div style={{ color: dark.dim, fontFamily: font.mono, fontSize: 13 }}>No messages yet.</div>
        )}
        {events?.map((event) => (
          <ChatLine key={event.id} event={event} user={user} handles={handles} now={now} />
        ))}
        <div style={{ color: hint.color, fontFamily: font.mono, fontSize: 13, whiteSpace: 'pre-wrap' }}>
          <span aria-hidden="true" style={{ animation: hint.blink ? 'wb-blink 1s linear infinite' : 'none' }}>
            ▍
          </span>{' '}
          {hint.text}
        </div>
      </div>
    </div>
  )
}

const mono: CSSProperties = { fontFamily: font.mono, fontSize: 12, lineHeight: '18px', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }

function Meta({ who, event, now, align = 'left' }: { who: string; event: ChatEvent; now: number; align?: 'left' | 'right' }) {
  return (
    <div style={{ display: 'flex', gap: 8, justifyContent: align === 'right' ? 'flex-end' : 'flex-start', fontSize: 11, color: dark.dim }}>
      <span style={{ fontWeight: 600, color: dark.sub }}>{who}</span>
      {event.comment_id !== null && <span>ticket comment</span>}
      <span title={event.created_at}>{formatRelative(event.created_at, now)}</span>
      {event.queued && <QueuedTag />}
    </div>
  )
}

function QueuedTag() {
  return (
    <span
      title="Not delivered yet: the task is busy and takes it as its next turn"
      style={{ padding: '0 6px', borderRadius: 999, border: `1px solid ${dark.ask}`, color: dark.ask, fontWeight: 600 }}
    >
      queued
    </span>
  )
}

function ChatLine({ event, user, handles, now }: { event: ChatEvent; user: User | undefined; handles: string[]; now: number }) {
  const aiName = user?.name ?? 'AI user'
  switch (event.kind) {
    case 'user':
      return (
        <div style={{ alignSelf: 'flex-end', maxWidth: '78%', display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Meta who="Pablo" event={event} now={now} align="right" />
          <div
            style={{
              padding: '8px 12px',
              borderRadius: '12px 12px 4px 12px',
              background: dark.userBubble,
              border: `1px solid ${event.queued ? dark.ask : dark.cmd}`,
              color: dark.bright,
              opacity: event.queued ? 0.8 : 1,
            }}
          >
            <Markdown text={event.text} handles={handles} />
          </div>
        </div>
      )
    case 'ai_user':
      return (
        <div style={{ alignSelf: 'flex-end', maxWidth: '78%', display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Meta
            who={event.from_task ? `${userName(event.from_task.ai_user_id)} · task ${event.from_task.task_id}` : 'AI user'}
            event={event}
            now={now}
            align="right"
          />
          <div
            style={{
              padding: '8px 12px',
              borderRadius: '12px 12px 4px 12px',
              background: dark.replyBubble,
              border: `1px solid ${event.queued ? dark.ask : dark.ok}`,
              color: dark.bright,
              opacity: event.queued ? 0.8 : 1,
            }}
          >
            <Markdown text={event.text} handles={handles} />
          </div>
        </div>
      )
    case 'reply':
      return (
        <div style={{ alignSelf: 'flex-start', maxWidth: '86%', display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Meta who={aiName} event={event} now={now} />
          <div
            style={{
              padding: '8px 12px',
              borderRadius: '12px 12px 12px 4px',
              background: dark.replyBubble,
              border: `1px solid ${dark.line}`,
              color: dark.bright,
            }}
          >
            <Markdown text={event.text} handles={handles} />
          </div>
        </div>
      )
    case 'assistant':
      return (
        <div style={{ maxWidth: '92%', color: dark.text, fontSize: 13, lineHeight: '20px' }}>
          <Markdown text={event.text} handles={handles} />
        </div>
      )
    case 'tool':
      return (
        <div style={{ ...mono, color: dark.dim }}>
          <span style={{ color: dark.cmd }}>● </span>
          {event.text}
        </div>
      )
    case 'notice':
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            padding: '8px 12px',
            borderRadius: 10,
            border: `1px dashed ${dark.button}`,
            background: dark.footer,
            color: dark.text,
            fontSize: 13,
            lineHeight: '20px',
          }}
        >
          <Meta who="AgentHub notice" event={event} now={now} />
          <Markdown text={event.text} handles={handles} />
        </div>
      )
    case 'system':
      return (
        <div style={{ ...mono, color: dark.sub, textAlign: 'center' }}>
          — {event.text} —{event.queued ? ' (queued)' : ''}
        </div>
      )
    case 'error':
      return (
        <div
          role="alert"
          style={{
            ...mono,
            padding: '6px 10px',
            borderRadius: 8,
            border: `1px solid ${dark.error}`,
            background: 'rgba(255, 155, 143, 0.08)',
            color: dark.error,
          }}
        >
          ✕ {event.text}
        </div>
      )
    default:
      return <div style={{ ...mono, color: dark.text }}>{(event as ChatEvent).text}</div>
  }
}

function MessageBox({ task }: { task: Task }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const voice = useDictation(setText)

  if (task.status === 'archived') {
    return (
      <div style={{ padding: '14px 20px', background: dark.footer, borderTop: `1px solid ${dark.line}`, color: dark.sub, fontSize: 13 }}>
        This task is archived. Its chat stays readable, and it takes no more messages.
      </div>
    )
  }

  const send = async () => {
    const body = text.trim()
    if (!body || busy) return
    voice.cancel()
    setBusy(true)
    setError(null)
    try {
      applyTaskDetail(await api.sendMessage(task.id, body))
      setText('')
      void loadTasks()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 12px 12px 20px', background: dark.footer, borderTop: `1px solid ${dark.line}` }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10 }}>
        <span aria-hidden="true" style={{ paddingBottom: 10, color: dark.cmd, fontFamily: font.mono, fontSize: 14, fontWeight: 700 }}>
          ❯
        </span>
        <textarea
          className="wb-term-input"
          aria-label="Message for the AI user"
          placeholder={
            task.status === 'running'
              ? 'Write a message. It is queued and delivered when the current turn ends.'
              : 'Write a message for the AI user, then press Enter. Shift+Enter for a new line.'
          }
          rows={2}
          autoFocus
          value={text}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send()
            }
          }}
          style={{
            flex: '1 1 auto',
            minWidth: 0,
            minHeight: 44,
            padding: '10px 4px',
            border: 0,
            borderRadius: 6,
            background: 'transparent',
            color: dark.bright,
            fontFamily: font.mono,
            fontSize: 13,
            lineHeight: '20px',
            resize: 'vertical',
          }}
        />
        <MicButton voice={voice} disabled={busy} darkMode />
        <Button kind="primary" onClick={() => void send()} disabled={busy || !text.trim()} style={{ minHeight: 44 }}>
          {busy ? 'Sending…' : 'Send'}
        </Button>
      </div>
      {voice.error && (
        <p role="alert" style={{ margin: 0, color: dark.error, fontSize: 13 }}>
          {voice.error}
        </p>
      )}
      {error && (
        <p role="alert" style={{ margin: 0, color: dark.error, fontSize: 13 }}>
          {error}
        </p>
      )}
    </div>
  )
}
