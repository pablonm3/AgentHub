import { useRef, useState, type DragEvent } from 'react'
import { api, type Ticket, type User } from './api'
import AddTicketForm from './AddTicketForm'
import { cardsOf, isAlreadyAt, positionFor } from './lib/board'
import {
  applyTicketDetail,
  findUser,
  loadTickets,
  moveTicketLocally,
  notifyError,
  openTicket,
  useAppState,
  userName,
} from './store'
import { color, font, pageTitle } from './theme'
import { Avatar, CommentIcon, EmptyState, PlusIcon, StatusPill } from './ui'

/** Move a ticket to a stage (before a card, or at the end) and save it. */
export function moveTicket(tickets: Ticket[], id: number, stage: string, beforeId: number | null): void {
  const ticket = tickets.find((t) => t.id === id)
  if (!ticket || beforeId === id) return
  if (isAlreadyAt(tickets, id, stage, beforeId)) return
  const position = positionFor(tickets, id, stage, beforeId)
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
        {stages.map((stage) => (
          <Column
            key={stage.id}
            stage={stage}
            cards={cardsOf(tickets, stage.id)}
            users={boot.users}
            onAdd={() => setAddingIn(stage.id)}
            highlighted={dragging !== null && dragOver === stage.id}
            fadedId={dragging}
            onDragOverColumn={() => {
              if (dragOver !== stage.id) setDragOver(stage.id)
            }}
            onDragStartCard={(ticket) => {
              dragId.current = ticket.id
              // Fade only after the browser has captured the drag image; the ref holds the id meanwhile.
              window.setTimeout(() => setDragging(ticket.id), 0)
            }}
            onDragEnd={endDrag}
            onDrop={(beforeId) => drop(stage.id, beforeId)}
          />
        ))}
      </div>
      {addingIn !== null && <AddTicketForm stageId={addingIn} onClose={() => setAddingIn(null)} />}
    </main>
  )
}

/** One stage of the board: header and count, its cards, the empty state and the "Add a card" button. */
function Column({
  stage,
  cards,
  users,
  onAdd,
  highlighted,
  fadedId,
  onDragOverColumn,
  onDragStartCard,
  onDragEnd,
  onDrop,
}: {
  stage: { id: string; name: string }
  cards: Ticket[]
  users: User[]
  onAdd: () => void
  highlighted: boolean
  fadedId: number | null
  onDragOverColumn: () => void
  onDragStartCard: (ticket: Ticket) => void
  onDragEnd: () => void
  onDrop: (beforeId: number | null) => void
}) {
  return (
    <section
      aria-label={stage.name}
      onDragOver={(e: DragEvent) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        onDragOverColumn()
      }}
      onDrop={(e: DragEvent) => {
        e.preventDefault()
        onDrop(null)
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
        boxShadow: `inset 0 0 0 2px ${highlighted ? color.accent : 'transparent'}`,
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
            assignee={findUser(users, ticket.assignee_id)}
            faded={fadedId === ticket.id}
            onDragStart={(e) => {
              e.dataTransfer.effectAllowed = 'move'
              try {
                e.dataTransfer.setData('text/plain', ticket.key)
              } catch {
                // Some browsers refuse custom drag data; the ref carries the id anyway.
              }
              onDragStartCard(ticket)
            }}
            onDragEnd={onDragEnd}
            onDrop={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onDrop(ticket.id)
            }}
          />
        ))}
      </div>
      {cards.length === 0 && <EmptyState compact>No cards here. Drop one in or add a card.</EmptyState>}
      <button
        type="button"
        className="wb-ghost"
        onClick={onAdd}
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
    </section>
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
        {ticket.task_status && (
          <StatusPill status={ticket.task_status} small waitingOn={ticket.task_waiting_on ? userName(ticket.task_waiting_on) : undefined} />
        )}
        <div style={{ display: 'flex', marginLeft: 'auto', paddingLeft: 6 }}>
          <Avatar user={assignee} size={26} />
        </div>
      </div>
    </div>
  )
}
