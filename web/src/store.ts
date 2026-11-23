// App state shared by every view. Data is refetched when the server publishes a topic on
// /api/events, and polled every few seconds in case the event stream drops.

import { useSyncExternalStore } from 'react'
import {
  api,
  ApiError,
  errorMessage,
  EVENTS_URL,
  type ActivityItem,
  type Bootstrap,
  type ServerEvent,
  type Task,
  type TaskDetail,
  type Ticket,
  type TicketDetail,
  type User,
} from './api'

export type Tab = 'board' | 'tasks' | 'activity' | 'settings'
const TABS: Tab[] = ['board', 'tasks', 'activity', 'settings']

export interface Notice {
  id: number
  kind: 'error' | 'warning' | 'info'
  text: string
}

export interface AppState {
  boot: Bootstrap | null
  bootError: string | null
  /** True while the server cannot be reached; cleared by the next successful request. */
  offline: boolean
  tickets: Ticket[]
  /** Every task, archived ones included (`GET /api/tasks?status=all`); pages filter locally. */
  tasks: Task[]
  activity: ActivityItem[]
  unseen: number
  tab: Tab
  openTicketId: number | null
  ticketDetail: TicketDetail | null
  openTaskId: number | null
  taskDetail: TaskDetail | null
  notices: Notice[]
  /** Server clock minus browser clock, applied to the live timers. */
  clockOffset: number
}

function tabFromHash(): Tab {
  const hash = typeof location === 'undefined' ? '' : location.hash.replace(/^#\/?/, '')
  return (TABS as string[]).includes(hash) ? (hash as Tab) : 'board'
}

let state: AppState = {
  boot: null,
  bootError: null,
  offline: false,
  tickets: [],
  tasks: [],
  activity: [],
  unseen: 0,
  tab: tabFromHash(),
  openTicketId: null,
  ticketDetail: null,
  openTaskId: null,
  taskDetail: null,
  notices: [],
  clockOffset: 0,
}

const listeners = new Set<() => void>()

function setState(patch: Partial<AppState>): void {
  state = { ...state, ...patch }
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getState(): AppState {
  return state
}

export function useAppState(): AppState {
  return useSyncExternalStore(subscribe, getState, getState)
}

/** The open ticket: its id, its loaded detail (null until loaded) and its board list item. */
export function useOpenTicket() {
  const s = useAppState()
  const id = s.openTicketId
  const detail = s.ticketDetail && s.ticketDetail.id === id ? s.ticketDetail : null
  return { id, detail, item: s.tickets.find((t) => t.id === id) }
}

/** The open task: its id, its loaded detail (null until loaded) and its list item. */
export function useOpenTask() {
  const s = useAppState()
  const id = s.openTaskId
  const detail = s.taskDetail && s.taskDetail.id === id ? s.taskDetail : null
  return { id, detail, item: s.tasks.find((t) => t.id === id) }
}

// ---- helpers over the state ----------------------------------------------------------------

export function serverNow(): number {
  return Date.now() + state.clockOffset
}

export function findUser(users: User[] | undefined, id: string | null | undefined): User | undefined {
  return users?.find((u) => u.id === id)
}

export function userName(id: string): string {
  return findUser(state.boot?.users, id)?.name ?? id
}

// ---- notices -------------------------------------------------------------------------------

let noticeSeq = 0

export function notify(kind: Notice['kind'], text: string): void {
  const notice = { id: ++noticeSeq, kind, text }
  setState({ notices: [...state.notices.slice(-3), notice] })
  window.setTimeout(() => dismissNotice(notice.id), kind === 'error' ? 12000 : 8000)
}

export function dismissNotice(id: number): void {
  if (state.notices.some((n) => n.id === id)) setState({ notices: state.notices.filter((n) => n.id !== id) })
}

/** Report a failed user action. */
export function notifyError(err: unknown): void {
  notify('error', errorMessage(err))
}

/** Run a write; on failure show the error notice, then reject so the caller can keep its edit open. */
export async function notifyOnFailure<T>(run: () => Promise<T>): Promise<T> {
  try {
    return await run()
  } catch (err) {
    notifyError(err)
    throw err
  }
}

/** Start a write nobody waits for: a failure is already shown by `notifyOnFailure`, so it is dropped here. */
export function runInBackground(write: Promise<unknown>): void {
  void write.catch(() => undefined)
}

// ---- loaders -------------------------------------------------------------------------------

/** Runs `fn` one at a time; a call made while it runs triggers exactly one more run. */
function serial(fn: () => Promise<void>): () => Promise<void> {
  let running: Promise<void> | null = null
  let again = false
  return () => {
    if (running) {
      again = true
      return running
    }
    running = (async () => {
      try {
        do {
          again = false
          await fn()
        } while (again)
      } finally {
        running = null
      }
    })()
    return running
  }
}

function markOfflineIfUnreachable(err: unknown): void {
  if (err instanceof ApiError && err.status === 0) {
    if (!state.offline) setState({ offline: true })
  }
}

function markOnline(): void {
  if (state.offline) setState({ offline: false })
}

function parseServerTime(value: string | number | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Date.parse(value)
    if (!Number.isNaN(parsed)) return parsed
  }
  return null
}

export const loadBoot = serial(async () => {
  try {
    const boot = await api.bootstrap()
    const server = parseServerTime(boot.server_time)
    const offset = server === null ? 0 : server - Date.now()
    // Same machine in practice; only correct a clear difference, not second-rounding noise.
    setState({ boot, bootError: null, clockOffset: Math.abs(offset) > 2000 ? offset : 0 })
    markOnline()
  } catch (err) {
    markOfflineIfUnreachable(err)
    if (!state.boot) setState({ bootError: errorMessage(err) })
  }
})

export const loadTickets = serial(async () => {
  try {
    const { tickets } = await api.tickets()
    setState({ tickets })
    markOnline()
  } catch (err) {
    markOfflineIfUnreachable(err)
  }
})

export const loadTasks = serial(async () => {
  try {
    const { tasks } = await api.tasks('all')
    setState({ tasks })
    markOnline()
  } catch (err) {
    markOfflineIfUnreachable(err)
  }
})

export const markSeen = serial(async () => {
  try {
    const { unseen } = await api.activitySeen()
    setState({ unseen })
  } catch (err) {
    markOfflineIfUnreachable(err)
  }
})

export const loadActivity = serial(async () => {
  try {
    const { items, unseen } = await api.activity()
    setState({ activity: items, unseen })
    markOnline()
    // Entries that arrive while the Activity tab is shown are seen.
    if (state.tab === 'activity' && unseen > 0) void markSeen()
  } catch (err) {
    markOfflineIfUnreachable(err)
  }
})

export const loadTicketDetail = serial(async () => {
  const id = state.openTicketId
  if (id === null) return
  try {
    const detail = await api.ticket(id)
    if (state.openTicketId === id) setState({ ticketDetail: detail })
  } catch (err) {
    markOfflineIfUnreachable(err)
    if (err instanceof ApiError && err.status === 404 && state.openTicketId === id) {
      setState({ openTicketId: null, ticketDetail: null })
      notify('warning', 'That ticket no longer exists.')
    }
  }
})

export const loadTaskDetail = serial(async () => {
  const id = state.openTaskId
  if (id === null) return
  try {
    const detail = await api.task(id)
    if (state.openTaskId === id) setState({ taskDetail: detail })
  } catch (err) {
    markOfflineIfUnreachable(err)
    if (err instanceof ApiError && err.status === 404 && state.openTaskId === id) {
      setState({ openTaskId: null, taskDetail: null })
      notify('warning', 'That task no longer exists.')
    }
  }
})

function loadAll(): void {
  void loadTickets()
  void loadTasks()
  void loadActivity()
  void loadTicketDetail()
  void loadTaskDetail()
}

// What each event topic covers. A task change also moves the card pill and the open ticket's
// Tasks block, and a new comment changes the open ticket and the Activity tab.
const TOPIC_LOADERS: Record<ServerEvent['topic'], Array<() => Promise<void>>> = {
  tickets: [loadTickets, loadTicketDetail, loadActivity],
  tasks: [loadTasks, loadTaskDetail, loadTicketDetail, loadTickets],
  activity: [loadActivity, loadTicketDetail],
  settings: [loadBoot],
  users: [loadBoot],
  projects: [loadBoot],
}

function loadersFor(topics: Iterable<ServerEvent['topic']>): Set<() => Promise<void>> {
  const loaders = new Set<() => Promise<void>>()
  for (const t of topics) for (const load of TOPIC_LOADERS[t] ?? []) loaders.add(load)
  return loaders
}

/** Refetch now what the given topics cover (TOPIC_LOADERS), e.g. after a write of this client. */
export function refresh(...topics: Array<ServerEvent['topic']>): void {
  for (const load of loadersFor(topics)) void load()
}

const pendingTopics = new Set<ServerEvent['topic']>()
let flushTimer: number | null = null

function refreshTopic(topic: ServerEvent['topic']): void {
  if (!(topic in TOPIC_LOADERS)) return
  pendingTopics.add(topic)
  if (flushTimer !== null) return
  // Coalesce bursts of events (a turn emits many) into one refetch per loader.
  flushTimer = window.setTimeout(() => {
    flushTimer = null
    const loaders = loadersFor(pendingTopics)
    pendingTopics.clear()
    for (const load of loaders) void load()
  }, 150)
}

// ---- live connection -----------------------------------------------------------------------

const POLL_MS = 5000
const BOOT_POLL_MS = 30000

/** Start loading, the event stream and the polling fallback. Returns a stop function. */
export function startLive(): () => void {
  void loadBoot()
  loadAll()

  let source: EventSource | null = null
  if (typeof EventSource !== 'undefined') {
    source = new EventSource(EVENTS_URL)
    source.onopen = () => {
      // Catch up on whatever happened while the stream was down.
      markOnline()
      loadAll()
    }
    source.onmessage = (msg: MessageEvent<string>) => {
      try {
        const event = JSON.parse(msg.data) as ServerEvent
        if (event && typeof event.topic === 'string') refreshTopic(event.topic)
      } catch {
        // A keep-alive or malformed line; the poll covers anything missed.
      }
    }
  }

  const poll = window.setInterval(() => {
    if (document.hidden) return
    loadAll()
  }, POLL_MS)
  const bootPoll = window.setInterval(() => {
    if (!document.hidden || !state.boot) void loadBoot()
  }, BOOT_POLL_MS)
  const onVisible = () => {
    if (!document.hidden) loadAll()
  }
  document.addEventListener('visibilitychange', onVisible)

  return () => {
    source?.close()
    window.clearInterval(poll)
    window.clearInterval(bootPoll)
    document.removeEventListener('visibilitychange', onVisible)
  }
}

// ---- navigation ----------------------------------------------------------------------------

export function setTab(tab: Tab): void {
  setState({ tab })
  if (typeof history !== 'undefined') history.replaceState(null, '', `#${tab}`)
  // The Activity page marks its entries seen when it opens.
  if (tab === 'activity') void loadActivity()
}

export function openTicket(id: number): void {
  setState({
    openTicketId: id,
    ticketDetail: state.ticketDetail?.id === id ? state.ticketDetail : null,
  })
  void loadTicketDetail()
}

export function closeTicket(): void {
  setState({ openTicketId: null, ticketDetail: null })
}

/** Opens a task dialog on top of whatever is shown; closing it shows that again. */
export function openTask(id: number): void {
  setState({ openTaskId: id, taskDetail: state.taskDetail?.id === id ? state.taskDetail : null })
  void loadTaskDetail()
}

export function closeTask(): void {
  setState({ openTaskId: null, taskDetail: null })
}

/** "View ticket" in a task dialog: show the task's ticket instead of the task. */
export function viewTicketOf(task: Task): void {
  if (task.ticket_id === null) return
  closeTask()
  openTicket(task.ticket_id)
}

// ---- results of user actions ---------------------------------------------------------------

export function applyTicketDetail(detail: TicketDetail): void {
  const tickets = state.tickets.some((t) => t.id === detail.id)
    ? state.tickets.map((t) => (t.id === detail.id ? { ...t, ...pickTicket(detail) } : t))
    : [...state.tickets, pickTicket(detail)]
  setState({
    tickets,
    ticketDetail: state.openTicketId === detail.id ? detail : state.ticketDetail,
  })
}

function pickTicket(detail: TicketDetail): Ticket {
  const { comments: _c, tasks: _t, session_tokens: _s, harness_tokens: _h, project_info: _p, warning: _w, ...ticket } =
    detail
  return ticket
}

export function applyTaskDetail(detail: TaskDetail): void {
  const { events: _events, ...task } = detail
  const tasks = state.tasks.some((t) => t.id === task.id)
    ? state.tasks.map((t) => (t.id === task.id ? task : t))
    : [task, ...state.tasks]
  setState({ tasks, taskDetail: state.openTaskId === detail.id ? detail : state.taskDetail })
  refresh('tickets')
}

/** Optimistic board move; the server's answer or the next refetch replaces it. */
export function moveTicketLocally(id: number, stage: string, position: number): void {
  setState({ tickets: state.tickets.map((t) => (t.id === id ? { ...t, stage, position } : t)) })
}

export function applyBoot(patch: Partial<Bootstrap>): void {
  if (state.boot) setState({ boot: { ...state.boot, ...patch } })
}

export function applyUser(user: User): void {
  if (!state.boot) return
  applyBoot({ users: state.boot.users.map((u) => (u.id === user.id ? user : u)) })
}
