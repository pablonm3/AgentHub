import { useState } from 'react'
import { api, type Task, type TaskStatus, type User } from './api'
import NewTaskForm from './NewTaskForm'
import { applyTaskDetail, findUser, notifyOnFailure, openTask, runInBackground, useAppState } from './store'
import { color, font, pageTitle } from './theme'
import { Avatar, Button, ChevronIcon, EditableTitle, EmptyState, PlusIcon, StatusPill, Timer, TokenCounts } from './ui'

type Filter = 'all' | TaskStatus

const FILTERS: Array<[Filter, string]> = [
  ['all', 'All'],
  ['running', 'Running'],
  ['waiting_on_user', 'Waiting on user'],
  ['done', 'Done'],
  ['archived', 'Archived'],
]

// Waiting on Pablo first, as in the prototype; newest first inside each group.
const RANK: Record<TaskStatus, number> = { waiting_on_user: 0, running: 1, done: 2, archived: 3 }

function matches(task: Task, filter: Filter): boolean {
  // "All" is every task that is not archived; archived ones only show under their own filter.
  return filter === 'all' ? task.status !== 'archived' : task.status === filter
}

export default function TasksPage() {
  const { boot, tasks } = useAppState()
  const [filter, setFilter] = useState<Filter>('all')
  const [creating, setCreating] = useState(false)
  if (!boot) return null

  const rows = tasks
    .filter((t) => matches(t, filter))
    .map((t, i) => ({ t, i }))
    .sort((a, b) => RANK[a.t.status] - RANK[b.t.status] || a.i - b.i)
    .map(({ t }) => t)

  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
        width: '100%',
        maxWidth: 1240,
        margin: '0 auto',
        padding: '24px 24px 40px',
      }}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <h1 style={pageTitle}>Tasks</h1>
          <p style={{ margin: 0, color: color.muted }}>
            Each task is an AI user's session, on a ticket or on its own. Open one to read its chat and send it a message.
          </p>
        </div>
        <Button kind="primary" onClick={() => setCreating(true)} style={{ minHeight: 44 }}>
          <PlusIcon />
          New task
        </Button>
      </div>
      <div role="group" aria-label="Filter tasks" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {FILTERS.map(([value, label]) => {
          const on = filter === value
          const count = tasks.filter((t) => matches(t, value)).length
          return (
            <button
              key={value}
              type="button"
              className="wb-ghost"
              aria-pressed={on}
              onClick={() => setFilter(value)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                minHeight: 44,
                padding: '0 14px',
                border: `1px solid ${on ? color.ink : color.line}`,
                borderRadius: 999,
                background: on ? color.ink : color.surface,
                color: on ? '#FFFFFF' : color.ink,
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              {label}
              <span
                style={{
                  minWidth: 22,
                  padding: '1px 7px',
                  borderRadius: 999,
                  background: on ? color.ink2 : color.chip,
                  color: on ? '#FFFFFF' : color.ink2,
                  fontSize: 12,
                  lineHeight: '16px',
                  textAlign: 'center',
                }}
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rows.map((task) => (
          <TaskRow key={task.id} task={task} user={findUser(boot.users, task.ai_user_id)} />
        ))}
      </div>
      {rows.length === 0 && (
        <EmptyState>No tasks with this status right now.</EmptyState>
      )}
      {creating && <NewTaskForm onClose={() => setCreating(false)} />}
    </main>
  )
}

function TaskRow({ task, user }: { task: Task; user: User | undefined }) {
  const archived = task.status === 'archived'
  const saveTitle = (title: string) => notifyOnFailure(async () => applyTaskDetail(await api.updateTask(task.id, { title })))
  const stop = () => runInBackground(notifyOnFailure(async () => applyTaskDetail(await api.stopTask(task.id))))

  return (
    <div
      role="button"
      tabIndex={0}
      className="wb-row"
      aria-label={`Open task ${task.display_title}`}
      onClick={() => openTask(task.id)}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          openTask(task.id)
        }
      }}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '8px 18px',
        width: '100%',
        minHeight: 64,
        padding: '12px 16px',
        background: archived ? color.page : color.surface,
        border: `1px solid ${color.line}`,
        borderRadius: 12,
        color: color.ink,
        cursor: 'pointer',
        opacity: archived ? 0.75 : 1,
      }}
    >
      <span style={{ flex: '0 0 150px', display: 'flex' }}>
        <StatusPill status={task.status} />
      </span>
      <span style={{ flex: '2 1 260px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontSize: 15, lineHeight: '20px', fontWeight: 600 }}>
          {archived ? (
            <span>{task.display_title}</span>
          ) : (
            <EditableTitle value={task.display_title} muted={task.title === null} onSave={saveTitle} />
          )}
        </span>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontFamily: font.mono,
            fontSize: 12,
            lineHeight: '16px',
            color: color.muted,
          }}
        >
          <Avatar user={user} size={18} ring="none" />
          {task.ticket_key ?? 'No ticket'} · {user?.name ?? task.ai_user_id}
        </span>
        {task.status_reason && (
          <span
            title={task.status_reason}
            style={{ color: color.warnInk, fontSize: 12, lineHeight: '16px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {task.status_reason}
          </span>
        )}
      </span>
      <span
        title="Model"
        style={{
          flex: '0 0 auto',
          padding: '2px 8px',
          borderRadius: 6,
          background: color.chip,
          color: color.ink2,
          fontFamily: font.mono,
          fontSize: 12,
          lineHeight: '16px',
        }}
      >
        {task.model}
      </span>
      <Timer task={task} style={{ flex: '0 0 64px', color: color.ink2, fontSize: 13 }} />
      <TokenCounts session={task.session_tokens} harness={task.harness_tokens} style={{ flex: '0 0 auto', color: color.ink2 }} />
      <span style={{ flex: '0 0 72px', display: 'flex', justifyContent: 'flex-end' }}>
        {task.status === 'running' && (
          <Button
            kind="outline"
            compact
            onClick={(e) => {
              e.stopPropagation()
              void stop()
            }}
            onKeyDown={(e) => e.stopPropagation()}
          >
            Stop
          </Button>
        )}
      </span>
      <ChevronIcon />
    </div>
  )
}
