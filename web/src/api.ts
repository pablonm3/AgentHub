// Types and fetch helpers for the AgentHub HTTP API. URLs are relative, so the built UI works
// on whatever port the server listens on.

export type UserKind = 'human' | 'ai'

export interface User {
  id: string
  name: string
  kind: UserKind
  handle: string
  initials: string
  color: string
  prompt: string
}

export interface Stage {
  id: string
  name: string
}

export interface Project {
  name: string
  default_base: string
  repo: string
  ready: boolean
}

export interface Login {
  logged_in: boolean
  method: string | null
  subscription: string | null
  expires_at: string | null
  detail: string | null
}

/** Why this machine cannot create a GitHub repository. */
export type GithubBlock = 'not_installed' | 'not_logged_in' | 'unknown'

/** Whether `gh` on the machine that runs AgentHub can create a GitHub repository. */
export interface GithubStatus {
  can_create: boolean
  reason: GithubBlock | null
}

export type TaskStatus = 'running' | 'waiting_on_user' | 'done' | 'archived'
export type TaskOrigin = 'assignment' | 'mention' | 'manual'

export interface HarnessRun {
  run_id: string
  status: string
  pending_kind: string | null
  tokens: number
}

export interface Task {
  id: number
  ticket_id: number | null
  ticket_key: string | null
  ticket_title: string | null
  ai_user_id: string
  origin: TaskOrigin
  title: string | null
  display_title: string
  title_source: 'ai' | 'human' | null
  model: string
  status: TaskStatus
  status_reason: string | null
  open: boolean
  running_ms: number
  running_since: number | null
  session_tokens: number
  harness_tokens: number
  harness_runs: HarnessRun[]
  created_at: string
  updated_at: string
}

export type ChatEventKind = 'user' | 'notice' | 'assistant' | 'tool' | 'reply' | 'system' | 'error'

export interface ChatEvent {
  id: number
  kind: ChatEventKind
  text: string
  created_at: string
  comment_id: number | null
  queued: boolean
}

export interface TaskDetail extends Task {
  events: ChatEvent[]
}

export interface TaskRef {
  task_id: number
  ai_user_id: string
}

export interface Comment {
  id: number
  ticket_id: number
  author_id: string
  body: string
  task_id: number | null
  reply_to_id: number | null
  created_at: string
  delivered_to: TaskRef[]
  started: TaskRef[]
}

export interface Ticket {
  id: number
  key: string
  title: string
  description: string
  stage: string
  position: number
  assignee_id: string
  model: string
  project: string | null
  labels: string[]
  comment_count: number
  task_status: TaskStatus | null
  created_at: string
  updated_at: string
}

export interface TicketDetail extends Ticket {
  comments: Comment[]
  tasks: Task[]
  session_tokens: number
  harness_tokens: number
  project_info: Project | null
  warning?: string
}

/** The last figure one limit of the Claude account reported in a turn or a harness step. */
export interface UsageFigure {
  /** The limit's window as Claude names it: `seven_day`, `five_hour`, `seven_day_overage_included`, … */
  limit: string
  /** Share used, 0 to 1; null only for a reached limit that reported no share. */
  used: number | null
  /** Epoch seconds. */
  resets_at: number
  reached: boolean
  read_at: string
}

export interface Bootstrap {
  users: User[]
  stages: Stage[]
  models: string[]
  default_model: string
  projects: Project[]
  login: Login
  github: GithubStatus
  /** One entry per known limit; empty when none is known. */
  usage: UsageFigure[]
  server_time: string | number
}

export interface ActivityItem {
  comment: Comment
  ticket: { id: number; key: string; title: string }
  ai_user_id: string
  task_id: number | null
}

export interface ActivityList {
  items: ActivityItem[]
  unseen: number
}

export interface CommentResult {
  comment: Comment
  delivered_to: number[]
  started: number[]
}

export type TicketPatch = Partial<
  Pick<Ticket, 'title' | 'description' | 'stage' | 'position' | 'assignee_id' | 'model'>
>

interface NewTicketBase {
  title: string
  description: string
  stage: string
  assignee_id: string
  model: string
}

// Exactly one of `project` (a registered name, or null for "No project") and `new_project`.
export type NewTicket =
  | (NewTicketBase & { project: string | null })
  | (NewTicketBase & { new_project: { name: string; repo_url?: string } })

export type TaskFilter = TaskStatus | 'all'

/** A refused request: `message` is the server's text, `body` the parsed answer. */
export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

/** The body of a refusal as an object, so callers can read extra fields such as `created_repo`. */
export function errorBody(err: unknown): Record<string, unknown> {
  if (err instanceof ApiError && err.body && typeof err.body === 'object') {
    return err.body as Record<string, unknown>
  }
  return {}
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return String(err)
}

function messageOf(status: number, statusText: string, body: unknown): string {
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>
    if (typeof b.message === 'string' && b.message) return b.message
    if (typeof b.detail === 'string' && b.detail) return b.detail
    if (Array.isArray(b.detail)) {
      const parts = b.detail
        .map((d) => (d && typeof d === 'object' ? (d as Record<string, unknown>).msg : null))
        .filter((m): m is string => typeof m === 'string')
      if (parts.length) return parts.join('; ')
    }
  }
  if (typeof body === 'string' && body.trim()) return body.trim().slice(0, 300)
  return `Request failed: ${status} ${statusText}`.trim()
}

async function request<T>(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: 'application/json' } }
  if (method !== 'GET') {
    // The server refuses a mutation without a JSON body, so even an empty one is sent as {}.
    init.headers = { ...init.headers, 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body ?? {})
  }
  let res: Response
  try {
    res = await fetch(path, init)
  } catch (err) {
    throw new ApiError(`Cannot reach the AgentHub server (${errorMessage(err)})`, 0, null)
  }
  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!res.ok) throw new ApiError(messageOf(res.status, res.statusText, data), res.status, data)
  return data as T
}

const get = <T>(path: string) => request<T>('GET', path)
const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body)
const patch = <T>(path: string, body: unknown) => request<T>('PATCH', path, body)

export const api = {
  bootstrap: () => get<Bootstrap>('/api/bootstrap'),

  tickets: () => get<{ tickets: Ticket[] }>('/api/tickets'),
  ticket: (id: number) => get<TicketDetail>(`/api/tickets/${id}`),
  createTicket: (body: NewTicket) => post<TicketDetail>('/api/tickets', body),
  updateTicket: (id: number, body: TicketPatch) => patch<TicketDetail>(`/api/tickets/${id}`, body),
  comment: (ticketId: number, body: string, replyTo?: number) =>
    post<CommentResult>(
      `/api/tickets/${ticketId}/comments`,
      replyTo === undefined ? { body } : { body, reply_to: replyTo },
    ),

  tasks: (status?: TaskFilter) =>
    get<{ tasks: Task[] }>(status ? `/api/tasks?status=${encodeURIComponent(status)}` : '/api/tasks'),
  task: (id: number) => get<TaskDetail>(`/api/tasks/${id}`),
  createTask: (body: { ai_user_id: string; message: string; model: string }) =>
    post<TaskDetail>('/api/tasks', body),
  updateTask: (id: number, body: { title?: string; model?: string }) =>
    patch<TaskDetail>(`/api/tasks/${id}`, body),
  sendMessage: (id: number, text: string) => post<TaskDetail>(`/api/tasks/${id}/messages`, { text }),
  stopTask: (id: number) => post<TaskDetail>(`/api/tasks/${id}/stop`, {}),
  archiveTask: (id: number) => post<TaskDetail>(`/api/tasks/${id}/archive`, {}),

  activity: () => get<ActivityList>('/api/activity'),
  activitySeen: () => post<{ unseen: number }>('/api/activity/seen', {}),

  updateUser: (id: string, prompt: string) => patch<User>(`/api/users/${encodeURIComponent(id)}`, { prompt }),
  settings: () => get<{ default_model: string }>('/api/settings'),
  updateSettings: (default_model: string) => patch<{ default_model: string }>('/api/settings', { default_model }),
  login: () => get<Login>('/api/login'),
}

export interface ServerEvent {
  topic: 'tickets' | 'tasks' | 'activity' | 'settings' | 'users' | 'projects' | 'usage'
  id?: number
}

export const EVENTS_URL = '/api/events'
