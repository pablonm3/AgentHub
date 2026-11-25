import { useState, type ReactNode } from 'react'
import { api, type Comment, type Task, type TicketDetail, type TicketPatch, type User } from './api'
import CommentBox from './CommentBox'
import DescriptionField from './DescriptionField'
import { positionFor } from './lib/board'
import { deliveryLine } from './lib/delivery'
import { formatRelative, repoWebUrl } from './lib/format'
import {
  applyTicketDetail,
  closeTicket,
  findUser,
  notifyOnFailure,
  openTask,
  refresh,
  runInBackground,
  serverNow,
  useAppState,
  useOpenTicket,
  userName,
} from './store'
import { color, font, sectionHeading } from './theme'
import { Avatar, Button, CloseButton, Dialog, EditableTitle, ErrorText, Markdown, Select, StatusPill, Timer, TokenCounts } from './ui'
import { useDictation } from './voice'

export default function TicketDialog() {
  const s = useAppState()
  const { id, detail, item } = useOpenTicket()
  const ticket = detail ?? item
  if (id === null || !s.boot) return null

  const boot = s.boot
  const handles = boot.users.map((u) => u.handle)

  const save = (patch: TicketPatch) =>
    notifyOnFailure(async () => {
      applyTicketDetail(await api.updateTicket(id, patch))
      refresh('tickets', 'tasks')
    })
  const saveInBackground = (patch: TicketPatch) => runInBackground(save(patch))

  if (!ticket) {
    return (
      <Dialog label="Ticket" onClose={closeTicket}>
        <div style={{ display: 'flex', alignItems: 'center', padding: '10px 10px 24px 24px' }}>
          <p style={{ margin: 0, color: color.muted }}>Loading the ticket…</p>
          <span style={{ marginLeft: 'auto' }}>
            <CloseButton label="Close card" onClick={closeTicket} />
          </span>
        </div>
      </Dialog>
    )
  }

  const stageName = boot.stages.find((g) => g.id === ticket.stage)?.name ?? ticket.stage

  return (
    <Dialog label={ticket.title} onClose={closeTicket} maxWidth={960}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 10px 0 24px' }}>
        <span
          style={{
            fontFamily: font.mono,
            fontSize: 12,
            lineHeight: '16px',
            fontWeight: 500,
            padding: '3px 8px',
            borderRadius: 6,
            background: color.chip,
            color: color.ink2,
          }}
        >
          {ticket.key}
        </span>
        <span style={{ color: color.muted, fontSize: 13 }}>{stageName}</span>
        <span style={{ marginLeft: 'auto' }}>
          <CloseButton label="Close card" onClick={closeTicket} />
        </span>
      </div>
      <h2
        style={{
          margin: '2px 24px 0',
          fontFamily: font.display,
          fontSize: 23,
          lineHeight: '30px',
          fontWeight: 700,
          letterSpacing: '-0.01em',
        }}
      >
        <EditableTitle value={ticket.title} ariaLabel="Edit ticket title" onSave={(title) => save({ title })} />
      </h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px 32px', padding: '20px 24px 24px' }}>
        <div style={{ flex: '999 1 380px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 22 }}>
          <Description text={ticket.description} onSave={(description) => save({ description })} />
          {detail ? (
            <Comments detail={detail} users={boot.users} handles={handles} />
          ) : (
            <p style={{ margin: 0, color: color.muted }}>Loading comments…</p>
          )}
        </div>
        <aside style={{ flex: '1 1 280px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 22 }}>
          <Section title="Stage">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {boot.stages.map((g) => {
                const on = g.id === ticket.stage
                return (
                  <button
                    key={g.id}
                    type="button"
                    className="wb-ghost"
                    aria-pressed={on}
                    onClick={() => {
                      if (on) return
                      saveInBackground({ stage: g.id, position: positionFor(s.tickets, ticket.id, g.id, null) })
                    }}
                    style={{
                      minHeight: 40,
                      padding: '0 14px',
                      border: `1px solid ${on ? color.ink : color.line}`,
                      borderRadius: 999,
                      background: on ? color.ink : color.surface,
                      color: on ? '#FFFFFF' : color.ink,
                      fontSize: 13,
                      fontWeight: 600,
                    }}
                  >
                    {g.name}
                  </button>
                )
              })}
            </div>
          </Section>
          <Section title="Assigned to">
            <Select
              ariaLabel="Assigned to"
              value={ticket.assignee_id}
              onChange={(assignee_id) => saveInBackground({ assignee_id })}
              options={boot.users.map((u) => ({ value: u.id, label: u.name }))}
            />
          </Section>
          <Section title="Model">
            <Select
              ariaLabel="Model"
              value={ticket.model}
              onChange={(model) => saveInBackground({ model })}
              options={boot.models.map((m) => ({ value: m, label: m }))}
            />
          </Section>
          <Section title="Project">
            <ProjectInfo detail={detail} project={ticket.project} />
          </Section>
          {(ticket.labels ?? []).length > 0 && (
            <Section title="Labels">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {(ticket.labels ?? []).map((label) => (
                  <span
                    key={label}
                    style={{
                      padding: '3px 9px',
                      borderRadius: 6,
                      background: color.chip,
                      color: color.ink2,
                      fontSize: 12,
                      lineHeight: '16px',
                      fontWeight: 600,
                    }}
                  >
                    {label}
                  </span>
                ))}
              </div>
            </Section>
          )}
          {detail && <TasksBlock detail={detail} users={boot.users} />}
        </aside>
      </div>
    </Dialog>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <h3 style={sectionHeading}>{title}</h3>
      {children}
    </section>
  )
}

function Description({ text, onSave }: { text: string; onSave: (text: string) => Promise<void> }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(text)
  const [busy, setBusy] = useState(false)
  const voice = useDictation(setDraft)

  const save = async () => {
    voice.cancel()
    setBusy(true)
    try {
      await onSave(draft.trim())
      setEditing(false)
    } catch {
      // Reported by onSave; the draft stays so nothing is lost.
    } finally {
      setBusy(false)
    }
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <h3 style={sectionHeading}>Description</h3>
        {!editing && (
          <Button
            kind="ghost"
            compact
            onClick={() => {
              setDraft(text)
              setEditing(true)
            }}
            style={{ marginLeft: 'auto' }}
          >
            Edit
          </Button>
        )}
      </div>
      {editing ? (
        <>
          <DescriptionField
            value={draft}
            onChange={setDraft}
            voice={voice}
            minRows={10}
            disabled={busy}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation()
                setEditing(false)
              } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                void save()
              }
            }}
          />
          {voice.error && <ErrorText>{voice.error}</ErrorText>}
          <div style={{ display: 'flex', gap: 8 }}>
            <Button kind="primary" onClick={() => void save()} disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </Button>
            <Button kind="ghost" onClick={() => setEditing(false)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </>
      ) : text.trim() ? (
        <Markdown text={text} style={{ fontSize: 15, lineHeight: '23px' }} />
      ) : (
        <p style={{ margin: 0, color: color.muted }}>No description yet.</p>
      )}
    </section>
  )
}

function Comments({ detail, users, handles }: { detail: TicketDetail; users: User[]; handles: string[] }) {
  const now = serverNow()
  const comments = detail.comments ?? []
  const n = comments.length
  const byId = new Map(comments.map((c) => [c.id, c]))

  const post = async (body: string) => {
    await api.comment(detail.id, body)
    refresh('tickets', 'tasks', 'activity')
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <h3 style={sectionHeading}>{n === 1 ? '1 comment' : `${n} comments`}</h3>
      {n === 0 && <p style={{ margin: 0, color: color.muted }}>No comments yet. Start the thread below.</p>}
      {comments.map((c) => (
        <CommentView key={c.id} comment={c} users={users} handles={handles} now={now} replyTo={c.reply_to_id ? byId.get(c.reply_to_id) : undefined} />
      ))}
      <div style={{ paddingTop: 4 }}>
        <CommentBox onSubmit={post} />
      </div>
    </section>
  )
}

function CommentView({
  comment,
  users,
  handles,
  now,
  replyTo,
}: {
  comment: Comment
  users: User[]
  handles: string[]
  now: number
  replyTo: Comment | undefined
}) {
  const author = findUser(users, comment.author_id)
  const human = author ? author.kind === 'human' : comment.author_id === 'pablo'
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      <Avatar user={author} size={30} ring="none" />
      <div style={{ flex: '1 1 auto', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '0 8px' }}>
          <span style={{ fontWeight: 600 }}>{author?.name ?? comment.author_id}</span>
          <span style={{ color: color.muted, fontSize: 12 }} title={comment.created_at}>
            {formatRelative(comment.created_at, now)}
          </span>
          {replyTo && (
            <span style={{ color: color.muted, fontSize: 12 }}>
              replying to {userName(replyTo.author_id)}
            </span>
          )}
        </div>
        <Markdown text={comment.body} handles={handles} style={{ lineHeight: '22px' }} />
        {human && (
          <span style={{ color: color.muted, fontSize: 12, lineHeight: '16px' }}>{deliveryLine(comment, userName)}</span>
        )}
        {!human && comment.task_id !== null && (
          <span>
            <button
              type="button"
              onClick={() => openTask(comment.task_id as number)}
              style={{ padding: 0, border: 0, background: 'transparent', color: color.accentInk, fontSize: 12, fontWeight: 600 }}
            >
              Open task
            </button>
          </span>
        )}
      </div>
    </div>
  )
}

function ProjectInfo({ detail, project }: { detail: TicketDetail | null; project: string | null }) {
  if (!project) {
    return <p style={{ margin: 0, color: color.muted }}>No project. Its tasks cannot start a harness run.</p>
  }
  const info = detail?.project_info
  const link = repoWebUrl(info?.repo)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontWeight: 600 }}>{project}</span>
      {info && (
        <span style={{ fontFamily: font.mono, fontSize: 12, lineHeight: '18px', color: color.muted, overflowWrap: 'anywhere' }}>
          {link ? (
            <a href={link} target="_blank" rel="noopener noreferrer">
              {info.repo}
            </a>
          ) : (
            info.repo
          )}
        </span>
      )}
      {info && !info.ready && (
        <span style={{ color: color.warnInk, fontSize: 12 }}>Not ready for harness runs: its AGENTS.md is not filled in.</span>
      )}
      <span style={{ color: color.muted, fontSize: 12 }}>The project of a ticket cannot be changed.</span>
    </div>
  )
}

function TasksBlock({ detail, users }: { detail: TicketDetail; users: User[] }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h3 style={sectionHeading}>Tasks</h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, color: color.ink2, fontSize: 13 }}>
        <span style={{ color: color.muted }}>Total</span>
        <TokenCounts session={detail.session_tokens} harness={detail.harness_tokens} />
      </div>
      {(detail.tasks ?? []).length === 0 ? (
        <p style={{ margin: 0, color: color.muted }}>No task has worked on this ticket yet.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {(detail.tasks ?? []).map((task) => (
            <TaskSummary key={task.id} task={task} user={findUser(users, task.ai_user_id)} />
          ))}
        </div>
      )}
    </section>
  )
}

function TaskSummary({ task, user }: { task: Task; user: User | undefined }) {
  const archived = task.status === 'archived'
  return (
    <button
      type="button"
      className="wb-row"
      onClick={() => openTask(task.id)}
      aria-label={`Open task ${task.display_title}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        gap: 6,
        width: '100%',
        padding: '10px 12px',
        border: `1px solid ${color.line}`,
        borderRadius: 10,
        background: archived ? color.page : color.surface,
        color: color.ink,
        textAlign: 'left',
        opacity: archived ? 0.65 : 1,
      }}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <StatusPill status={task.status} small />
        <span
          style={{
            minWidth: 0,
            fontSize: 13,
            fontWeight: 600,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            color: task.title ? color.ink : color.muted,
            fontStyle: task.title ? undefined : 'italic',
          }}
        >
          {task.display_title}
        </span>
      </span>
      <span style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 10px', color: color.muted, fontSize: 12 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <Avatar user={user} size={18} ring="none" />
          {user?.name ?? task.ai_user_id}
        </span>
        <span style={{ fontFamily: font.mono }}>{task.model}</span>
        <Timer task={task} />
        <TokenCounts session={task.session_tokens} harness={task.harness_tokens} />
      </span>
    </button>
  )
}
