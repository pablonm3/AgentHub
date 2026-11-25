import { useEffect, type ReactNode } from 'react'
import ActivityPage from './ActivityPage'
import Board from './Board'
import SettingsPage from './SettingsPage'
import TaskDialog from './TaskDialog'
import TasksPage from './TasksPage'
import TicketDialog from './TicketDialog'
import type { UsageFigure } from './api'
import { formatRelative } from './lib/format'
import { formatResetTime, usageLines } from './lib/usage'
import { closeTask, closeTicket, dismissNotice, setTab, startLive, useAppState, type Notice, type Tab } from './store'
import { color, font } from './theme'
import { Avatar, BellIcon, BoardIcon, Button, Dialog, ErrorBoundary, GearIcon, TerminalIcon, useNow } from './ui'

export default function App() {
  const s = useAppState()
  useEffect(() => startLive(), [])

  const waiting = s.tasks.filter((t) => t.status === 'waiting_on_user').length

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: color.page,
        color: color.ink,
        fontFamily: font.sans,
        fontSize: 14,
        lineHeight: '20px',
      }}
    >
      <header
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '0 28px',
          padding: '0 24px',
          background: color.surface,
          borderBottom: `1px solid ${color.line}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 0' }}>
          <span
            aria-hidden="true"
            style={{ width: 28, height: 28, borderRadius: 8, background: color.accent, display: 'grid', placeItems: 'center' }}
          >
            <BoardIcon filled />
          </span>
          <span style={{ fontFamily: font.display, fontSize: 18, lineHeight: '24px', fontWeight: 700, letterSpacing: '-0.01em' }}>
            AgentHub
          </span>
        </div>
        <nav aria-label="Views" style={{ display: 'flex', alignSelf: 'stretch', gap: 4 }}>
          <TabButton tab="board" current={s.tab} icon={<BoardIcon />} label="Board" />
          <TabButton
            tab="tasks"
            current={s.tab}
            icon={<TerminalIcon />}
            label="Tasks"
            badge={waiting > 0 ? { count: waiting, title: 'Tasks waiting on you' } : undefined}
          />
          <TabButton
            tab="activity"
            current={s.tab}
            icon={<BellIcon />}
            label="Activity"
            badge={s.unseen > 0 ? { count: s.unseen, title: 'New AI comments' } : undefined}
          />
        </nav>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 16, padding: '12px 0' }}>
          {s.boot && <UsageLeft figures={s.boot.usage} />}
          <button
            type="button"
            className="wb-ghost"
            aria-current={s.tab === 'settings' ? 'page' : undefined}
            onClick={() => setTab('settings')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              minHeight: 40,
              padding: '0 12px',
              border: `1px solid ${s.tab === 'settings' ? color.accent : color.line}`,
              borderRadius: 9,
              background: s.tab === 'settings' ? color.accentSoft : color.surface,
              color: s.tab === 'settings' ? color.accentInk : color.ink2,
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            <GearIcon />
            Settings
          </button>
          <div style={{ display: 'flex', alignItems: 'center', paddingLeft: 8 }}>
            {(s.boot?.users ?? [])
              .slice()
              .reverse()
              .map((u) => (
                <Avatar key={u.id} user={u} size={32} overlap={8} />
              ))}
          </div>
        </div>
      </header>

      {s.offline && s.boot && (
        <div role="status" style={{ padding: '8px 24px', background: color.warnSoft, color: color.warnInk, fontSize: 13, fontWeight: 600 }}>
          Cannot reach the AgentHub server. Retrying…
        </div>
      )}

      {s.boot ? (
        <ErrorBoundary key={s.tab} fallback={(error, reset) => <ViewError error={error} onRetry={reset} />}>
          {s.tab === 'board' && <Board />}
          {s.tab === 'tasks' && <TasksPage />}
          {s.tab === 'activity' && <ActivityPage />}
          {s.tab === 'settings' && <SettingsPage />}
        </ErrorBoundary>
      ) : (
        <main style={{ flex: '1 1 auto', display: 'grid', placeItems: 'center', padding: 40 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center', textAlign: 'center' }}>
            <p style={{ margin: 0, fontWeight: 600 }}>{s.bootError ? 'Cannot reach the AgentHub server' : 'Loading AgentHub…'}</p>
            {s.bootError && (
              <p style={{ margin: 0, color: color.muted, fontSize: 13, maxWidth: 520 }}>
                {s.bootError}. Retrying every few seconds; start it with <code style={{ fontFamily: font.mono }}>agenthub serve</code>.
              </p>
            )}
          </div>
        </main>
      )}

      {s.boot && s.openTicketId !== null && (
        <ErrorBoundary key={`ticket-${s.openTicketId}`} fallback={(error) => <DialogError error={error} onClose={closeTicket} />}>
          <TicketDialog />
        </ErrorBoundary>
      )}
      {s.boot && s.openTaskId !== null && (
        <ErrorBoundary key={`task-${s.openTaskId}`} fallback={(error) => <DialogError error={error} onClose={closeTask} />}>
          <TaskDialog />
        </ErrorBoundary>
      )}
      <Notices notices={s.notices} />
    </div>
  )
}

const USAGE_TITLE =
  'The share of each limit of the Claude account still unused, as last reported by an AI turn or a harness step'

/** The account's usage left per limit; ages advance and ended periods drop out on a 30 s tick. */
function UsageLeft({ figures }: { figures: UsageFigure[] | undefined }) {
  const now = useNow(true, 30_000)
  const lines = usageLines(figures, now)
  if (lines.length === 0) {
    return (
      <span title={USAGE_TITLE} style={{ color: color.muted, fontSize: 12, lineHeight: '16px' }}>
        Usage left: not known
      </span>
    )
  }
  return (
    <div
      title={USAGE_TITLE}
      style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 14px', fontSize: 12, lineHeight: '16px' }}
    >
      <span style={{ color: color.muted, fontWeight: 600 }}>Usage left</span>
      {lines.map((line) => (
        <div key={line.limit} style={{ display: 'flex', flexDirection: 'column', whiteSpace: 'nowrap' }}>
          <span style={{ color: color.ink, fontWeight: 600 }}>
            {line.percentLeft === null ? `${line.label} limit reached` : `${line.label} ${line.percentLeft}%`}
          </span>
          <span style={{ color: color.muted }}>
            {`resets ${formatResetTime(line.resetsAt)} · read ${formatRelative(line.readAt, now)}`}
          </span>
        </div>
      ))}
    </div>
  )
}

function ViewError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <main style={{ padding: 40, display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-start' }}>
      <p style={{ margin: 0, fontWeight: 600 }}>This view could not be shown.</p>
      <p style={{ margin: 0, color: color.muted, fontFamily: font.mono, fontSize: 12 }}>{error.message}</p>
      <Button onClick={onRetry}>Try again</Button>
    </main>
  )
}

function DialogError({ error, onClose }: { error: Error; onClose: () => void }) {
  return (
    <Dialog label="Error" onClose={onClose} maxWidth={520}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 24 }}>
        <p style={{ margin: 0, fontWeight: 600 }}>This could not be shown.</p>
        <p style={{ margin: 0, color: color.muted, fontFamily: font.mono, fontSize: 12 }}>{error.message}</p>
        <div>
          <Button onClick={onClose}>Close</Button>
        </div>
      </div>
    </Dialog>
  )
}

function TabButton({
  tab,
  current,
  icon,
  label,
  badge,
}: {
  tab: Tab
  current: Tab
  icon: ReactNode
  label: string
  badge?: { count: number; title: string }
}) {
  const on = tab === current
  return (
    <button
      type="button"
      className="wb-ghost"
      onClick={() => setTab(tab)}
      aria-current={on ? 'page' : undefined}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        minHeight: 56,
        padding: '0 14px',
        background: 'transparent',
        borderStyle: 'solid',
        borderColor: on ? color.accent : 'transparent',
        borderWidth: '0 0 3px 0',
        color: on ? color.ink : color.muted,
        fontSize: 14,
        fontWeight: 600,
      }}
    >
      {icon}
      {label}
      {badge && (
        <span
          title={badge.title}
          style={{
            minWidth: 22,
            padding: '2px 7px',
            borderRadius: 999,
            background: color.warnSoft,
            color: color.warnInk,
            fontSize: 12,
            lineHeight: '16px',
            fontWeight: 600,
            textAlign: 'center',
          }}
        >
          {badge.count}
        </span>
      )}
    </button>
  )
}

function Notices({ notices }: { notices: Notice[] }) {
  if (notices.length === 0) return null
  return (
    <div
      aria-live="polite"
      style={{
        position: 'fixed',
        right: 16,
        bottom: 16,
        zIndex: 80,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        maxWidth: 'min(440px, calc(100vw - 32px))',
      }}
    >
      {notices.map((n) => (
        <div
          key={n.id}
          role={n.kind === 'error' ? 'alert' : 'status'}
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 10,
            padding: '10px 12px',
            borderRadius: 10,
            background: n.kind === 'error' ? color.errorSoft : n.kind === 'warning' ? color.warnSoft : color.surface,
            color: n.kind === 'error' ? color.errorInk : n.kind === 'warning' ? color.warnInk : color.ink,
            border: `1px solid ${color.line}`,
            boxShadow: '0 8px 24px rgba(15, 18, 24, 0.16)',
            fontSize: 13,
            lineHeight: '18px',
            overflowWrap: 'anywhere',
          }}
        >
          <span style={{ flex: '1 1 auto' }}>{n.text}</span>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => dismissNotice(n.id)}
            style={{ border: 0, background: 'transparent', color: 'inherit', fontWeight: 700, padding: 0 }}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
