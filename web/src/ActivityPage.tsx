import { useEffect, useState } from 'react'
import { api, type ActivityItem, type Comment } from './api'
import CommentBox from './CommentBox'
import { deliveryLine } from './lib/delivery'
import { formatRelative } from './lib/format'
import {
  findUser,
  markSeen,
  openTask,
  openTicket,
  refresh,
  serverNow,
  useAppState,
  userName,
} from './store'
import { color, font, pageTitle } from './theme'
import { Avatar, Button, EmptyState, Markdown } from './ui'

/** The comments AI users posted on tickets, newest first, each with a reply box. */
export default function ActivityPage() {
  const { boot, activity } = useAppState()
  // Replies sent from this page, per entry (comment id), with who received them.
  const [sent, setSent] = useState<Record<number, Comment[]>>({})

  useEffect(() => {
    void markSeen()
  }, [])

  if (!boot) return null
  const handles = boot.users.map((u) => u.handle)
  const now = serverNow()

  const reply = async (item: ActivityItem, body: string) => {
    const result = await api.comment(item.ticket.id, body, item.comment.id)
    setSent((prev) => ({ ...prev, [item.comment.id]: [...(prev[item.comment.id] ?? []), result.comment] }))
    refresh('activity', 'tasks', 'tickets')
  }

  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
        width: '100%',
        maxWidth: 920,
        margin: '0 auto',
        padding: '24px 24px 40px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <h1 style={pageTitle}>Activity</h1>
        <p style={{ margin: 0, color: color.muted }}>
          What the AI users posted on tickets, newest first. Reply here without opening the ticket.
        </p>
      </div>
      {activity.length === 0 && (
        <EmptyState>No AI comments yet.</EmptyState>
      )}
      {activity.map((item) => {
        const author = findUser(boot.users, item.ai_user_id) ?? findUser(boot.users, item.comment.author_id)
        const replies = sent[item.comment.id] ?? []
        return (
          <article
            key={item.comment.id}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
              padding: 16,
              background: color.surface,
              border: `1px solid ${color.line}`,
              borderRadius: 12,
            }}
          >
            <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 10px' }}>
              <Avatar user={author} size={30} ring="none" />
              <span style={{ fontWeight: 600 }}>{author?.name ?? item.ai_user_id}</span>
              <span style={{ color: color.muted, fontSize: 13 }}>on</span>
              <button
                type="button"
                onClick={() => openTicket(item.ticket.id)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'baseline',
                  gap: 6,
                  minWidth: 0,
                  padding: 0,
                  border: 0,
                  background: 'transparent',
                  color: color.accentInk,
                  fontSize: 14,
                  fontWeight: 600,
                  textAlign: 'left',
                }}
              >
                <span style={{ fontFamily: font.mono, fontSize: 12 }}>{item.ticket.key}</span>
                <span style={{ overflowWrap: 'anywhere' }}>{item.ticket.title}</span>
              </button>
              <span style={{ marginLeft: 'auto', color: color.muted, fontSize: 12 }} title={item.comment.created_at}>
                {formatRelative(item.comment.created_at, now)}
              </span>
            </header>
            <Markdown text={item.comment.body} handles={handles} style={{ lineHeight: '22px' }} />
            {item.task_id !== null && (
              <div>
                <Button kind="ghost" compact onClick={() => openTask(item.task_id as number)} style={{ color: color.accentInk, paddingLeft: 0 }}>
                  Open task
                </Button>
              </div>
            )}
            {replies.map((r) => (
              <div
                key={r.id}
                style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '8px 10px', borderRadius: 8, background: color.page }}
              >
                <span style={{ fontSize: 12, fontWeight: 600, color: color.ink2 }}>You replied</span>
                <Markdown text={r.body} handles={handles} />
                <span style={{ color: color.muted, fontSize: 12, lineHeight: '16px' }}>{deliveryLine(r, userName)}</span>
              </div>
            ))}
            <CommentBox
              label={`Reply to ${author?.name ?? 'this comment'}`}
              hideLabel
              rows={2}
              placeholder={`Reply to ${author?.name ?? 'the AI user'}. Type @ to tag someone.`}
              onSubmit={(body) => reply(item, body)}
            />
          </article>
        )
      })}
    </main>
  )
}
