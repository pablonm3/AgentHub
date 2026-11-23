import { useRef, useState, type DragEvent } from 'react'
import { api, type Ticket, type User } from './api'
import AddTicketForm from './AddTicketForm'
import { cardsOf, positionFor } from './lib/board'
import {
  applyTicketDetail,
  findUser,
  loadTickets,
  moveTicketLocally,
  notifyError,
  openTicket,
  useAppState,
} from './store'
import { color, font, pageTitle } from './theme'
import { Avatar, CommentIcon, PlusIcon, StatusPill } from './ui'

/** Move a ticket to a stage (before a card, or at the end) and save it. */
export function moveTicket(tickets: Ticket[], id: number, stage: string, beforeId: number | null): void {
  const ticket = tickets.find((t) => t.id === id)
  if (!ticket || beforeId === id) return
  const position = positionFor(tickets, id, stage, beforeId)
  const column = cardsOf(tickets, stage).map((t) => t.id)
  const unchanged =
    ticket.stage === stage &&
    (beforeId === null ? column[column.length - 1] === id : column[column.indexOf(beforeId) - 1] === id)
  if (unchanged) return
  moveTicketLocally(id, stage, position)
  api
    .updateTicket(id, { stage, position })
    .then(applyTicketDetail)
    .catch((err) => {
      notifyError(err)
      void loadTickets()
    })
}

export default function Board() {
  const { boot, tickets } = useAppState()
  const [addingIn, setAddingIn] = useState<string | null>(null)
  const [dragging, setDragging] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState<string | null>(null)
  const dragId = useRef<number | null>(null)

  if (!boot) return null
  const stages = boot.stages
  const total = tickets.length

  const endDrag = () => {
    dragId.current = null
    setDragging(null)
    setDragOver(null)
  }
  const drop = (stage: string, beforeId: number | null) => {
    const id = dragId.current
    endDrag()
    if (id !== null) moveTicket(tickets, id, stage, beforeId)
  }

  return (
    <main style={{ display: 'flex', flexDirection: 'column', flex: '1 1 auto', minWidth: 0 }}>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: '8px 24px',
          padding: '24px 24px 16px',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <h1 style={pageTitle}>AgentHub board</h1>
          <p style={{ margin: 0, color: color.muted }}>
            {total} {total === 1 ? 'card' : 'cards'} across {stages.length} stages
          </p>
        </div>
        <p style={{ margin: 0, color: color.muted, fontSize: 13 }}>
          Drag a card to another stage, or open it to move, assign and comment.
        </p>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, padding: '0 24px 32px', overflowX: 'auto' }}>
        {stages.map((stage) => {
          const cards = cardsOf(tickets, stage.id)
          const adding = addingIn === stage.id
          return (
            <section
              key={stage.id}
              aria-label={stage.name}
              onDragOver={(e: DragEvent) => {
                e.preventDefault()
                e.dataTransfer.dropEffect = 'move'
                if (dragOver !== stage.id) setDragOver(stage.id)
              }}
              onDrop={(e: DragEvent) => {
                e.preventDefault()
                drop(stage.id, null)
              }}
              style={{
                flex: '1 0 256px',
                maxWidth: 380,
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                padding: 12,
                borderRadius: 12,
                background: color.column,
                boxShadow: `inset 0 0 0 2px ${dragging !== null && dragOver === stage.id ? color.accent : 'transparent'}`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '2px 4px' }}>
                <h2 style={{ margin: 0, fontFamily: font.display, fontSize: 15, lineHeight: '20px', fontWeight: 600 }}>
                  {stage.name}
                </h2>
                <span
                  style={{
                    minWidth: 26,
                    padding: '2px 8px',
                    borderRadius: 999,
                    background: color.surface,
                    color: color.ink2,
                    fontSize: 12,
                    lineHeight: '16px',
                    fontWeight: 600,
                    textAlign: 'center',
                  }}
                >
                  {cards.length}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {cards.map((ticket) => (
                  <Card
                    key={ticket.id}
                    ticket={ticket}
                    assignee={findUser(boot.users, ticket.assignee_id)}
                    faded={dragging === ticket.id}
                    onDragStart={(e) => {
                      dragId.current = ticket.id
                      e.dataTransfer.effectAllowed = 'move'
                      try {
                        e.dataTransfer.setData('text/plain', ticket.key)
                      } catch {
                        // Some browsers refuse custom drag data; the ref carries the id anyway.
                      }
                      window.setTimeout(() => setDragging(ticket.id), 0)
                    }}
                    onDragEnd={endDrag}
                    onDrop={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      drop(stage.id, ticket.id)
                    }}
                  />
                ))}
              </div>
              {cards.length === 0 && !adding && (
                <p
                  style={{
                    margin: 0,
                    padding: '18px 12px',
                    border: `1px dashed ${color.lineStrong}`,
                    borderRadius: 10,
                    color: color.muted,
                    fontSize: 13,
                    textAlign: 'center',
                  }}
                >
                  No cards here. Drop one in or add a card.
                </p>
              )}
              {adding ? (
                <AddTicketForm stageId={stage.id} onClose={() => setAddingIn(null)} />
              ) : (
                <button
                  type="button"
                  className="wb-ghost"
                  onClick={() => setAddingIn(stage.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    minHeight: 44,
                    padding: '0 10px',
                    border: 0,
                    borderRadius: 9,
                    background: 'transparent',
                    color: color.ink2,
                    fontSize: 13,
                    fontWeight: 600,
                    textAlign: 'left',
                  }}
                >
                  <PlusIcon />
                  Add a card
                </button>
              )}
            </section>
          )
        })}
      </div>
    </main>
  )
}

function Card({
  ticket,
  assignee,
  faded,
  onDragStart,
  onDragEnd,
  onDrop,
}: {
  ticket: Ticket
  assignee: User | undefined
  faded: boolean
  onDragStart: (e: DragEvent) => void
  onDragEnd: () => void
  onDrop: (e: DragEvent) => void
}) {
  const chips = [...(ticket.project ? [ticket.project] : []), ...(ticket.labels ?? [])]
  return (
    <div
      className="wb-card"
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: 12,
        background: color.surface,
        border: `1px solid ${color.line}`,
        borderRadius: 10,
        cursor: 'grab',
        opacity: faded ? 0.4 : 1,
      }}
    >
      {chips.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {chips.map((text, i) => (
            <span
              key={`${i}-${text}`}
              title={i === 0 && ticket.project ? 'Project' : 'Label'}
              style={{
                padding: '2px 8px',
                borderRadius: 6,
                background: color.chip,
                color: color.ink2,
                fontSize: 11,
                lineHeight: '16px',
                fontWeight: 600,
              }}
            >
              {text}
            </span>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => openTicket(ticket.id)}
        style={{
          display: 'flex',
          alignItems: 'center',
          width: '100%',
          minHeight: 44,
          padding: '2px 0',
          border: 0,
          background: 'transparent',
          color: color.ink,
          fontSize: 14,
          lineHeight: '20px',
          fontWeight: 600,
          textAlign: 'left',
          overflowWrap: 'anywhere',
        }}
      >
        {ticket.title}
      </button>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px 10px' }}>
        <span style={{ fontFamily: font.mono, fontSize: 12, lineHeight: '16px', color: color.muted }}>{ticket.key}</span>
        {ticket.comment_count > 0 && (
          <span
            title="Comments"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: color.muted, fontSize: 12, lineHeight: '16px' }}
          >
            <CommentIcon />
            {ticket.comment_count}
          </span>
        )}
        {ticket.task_status && <StatusPill status={ticket.task_status} small />}
        <div style={{ display: 'flex', marginLeft: 'auto', paddingLeft: 6 }}>
          <Avatar user={assignee} size={26} />
        </div>
      </div>
    </div>
  )
}
