// Renders every view from answers shaped like the API contract, through the store's own
// loaders, to catch render errors and check the labels the UI must show.

import { renderToStaticMarkup } from 'react-dom/server'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import ActivityPage from './ActivityPage'
import AddTicketForm from './AddTicketForm'
import App from './App'
import Board from './Board'
import DescriptionField from './DescriptionField'
import NewTaskForm from './NewTaskForm'
import SettingsPage from './SettingsPage'
import TaskDialog from './TaskDialog'
import TasksPage from './TasksPage'
import TicketDialog from './TicketDialog'
import type { Bootstrap, Comment, Task, TaskDetail, Ticket, TicketDetail } from './api'
import {
  getState,
  loadActivity,
  loadBoot,
  loadTaskDetail,
  loadTasks,
  loadTicketDetail,
  loadTickets,
  openTask,
  openTicket,
} from './store'
import type { Dictation } from './voice'

const NOW = Date.now()

const boot: Bootstrap = {
  users: [
    { id: 'pablo', name: 'Pablo', kind: 'human', handle: 'Pablo', initials: 'PA', color: '#161A22', prompt: '' },
    { id: 'data_scientist', name: 'Data Scientist', kind: 'ai', handle: 'DataScientist', initials: 'DS', color: '#7A3FB5', prompt: 'You are the data scientist.' },
    { id: 'engineer', name: 'Engineer', kind: 'ai', handle: 'Engineer', initials: 'EN', color: '#0F7B6C', prompt: 'You are the engineer.' },
    { id: 'devops', name: 'DevOps', kind: 'ai', handle: 'DevOps', initials: 'DO', color: '#B4531A', prompt: 'You are DevOps.' },
  ],
  stages: [
    { id: 'backlog', name: 'Backlog' },
    { id: 'todo', name: 'To do' },
    { id: 'in_progress', name: 'In progress' },
    { id: 'in_review', name: 'In review' },
    { id: 'done', name: 'Done' },
  ],
  models: ['fable', 'opus', 'sonnet', 'haiku'],
  default_model: 'opus',
  projects: [{ name: 'AgentHub', default_base: 'main', repo: 'git@github.com:owner/AgentHub.git', ready: true }],
  login: { logged_in: true, method: 'claude.ai', subscription: 'max', expires_at: null, detail: 'ok' },
  server_time: new Date(NOW).toISOString(),
}

function task(over: Partial<Task>): Task {
  return {
    id: 1,
    ticket_id: 1,
    ticket_key: 'AH-1',
    ticket_title: 'Add retries',
    ai_user_id: 'engineer',
    origin: 'assignment',
    title: 'Retry the webhook sender',
    display_title: 'Retry the webhook sender',
    title_source: 'ai',
    model: 'opus',
    status: 'running',
    status_reason: null,
    open: true,
    running_ms: 42_000,
    running_since: NOW - 1000,
    session_tokens: 12_345,
    harness_tokens: 3000,
    harness_runs: [{ run_id: 'retries_1', status: 'running', pending_kind: null, tokens: 3000 }],
    created_at: '2026-11-23T10:00:00Z',
    updated_at: '2026-11-23T10:05:00Z',
    ...over,
  }
}

const tasks: Task[] = [
  task({ id: 3 }),
  task({ id: 4, ai_user_id: 'devops', status: 'archived', title: null, display_title: 'Check the deploy', running_since: null, session_tokens: 950, harness_tokens: 0, harness_runs: [] }),
  task({ id: 5, ticket_id: null, ticket_key: null, ticket_title: null, origin: 'manual', ai_user_id: 'data_scientist', status: 'waiting_on_user', running_since: null, status_reason: 'Not logged in' }),
]

const ticket: Ticket = {
  id: 1,
  key: 'AH-1',
  title: 'Add retries',
  description: 'Retry failed deliveries. See https://example.com/spec',
  stage: 'in_progress',
  position: 1,
  assignee_id: 'engineer',
  model: 'opus',
  project: 'AgentHub',
  labels: [],
  comment_count: 3,
  task_status: 'running',
  created_at: '2026-11-23T10:00:00Z',
  updated_at: '2026-11-23T10:05:00Z',
}

const comments: Comment[] = [
  { id: 10, ticket_id: 1, author_id: 'pablo', body: 'Please look, @Engineer and @DevOps', task_id: null, reply_to_id: null, created_at: '2026-11-23T10:01:00Z', delivered_to: [{ task_id: 3, ai_user_id: 'engineer' }], started: [{ task_id: 4, ai_user_id: 'devops' }] },
  { id: 11, ticket_id: 1, author_id: 'engineer', body: 'Done, see [the report](/reports/3/report.html)', task_id: 3, reply_to_id: null, created_at: '2026-11-23T10:02:00Z', delivered_to: [], started: [] },
  { id: 12, ticket_id: 1, author_id: 'pablo', body: 'Thanks', task_id: null, reply_to_id: 11, created_at: '2026-11-23T10:03:00Z', delivered_to: [], started: [] },
]

const ticketDetail: TicketDetail = {
  ...ticket,
  comments,
  tasks: [tasks[0], tasks[1]],
  session_tokens: 13_295,
  harness_tokens: 3000,
  project_info: boot.projects[0],
}

const taskDetail: TaskDetail = {
  ...tasks[0],
  events: [
    { id: 1, kind: 'notice', text: 'Ticket AH-1: Add retries', created_at: '2026-11-23T10:00:00Z', comment_id: null, queued: false },
    { id: 2, kind: 'tool', text: 'Read src/sender.py', created_at: '2026-11-23T10:00:01Z', comment_id: null, queued: false },
    { id: 3, kind: 'assistant', text: 'Looking at the sender.', created_at: '2026-11-23T10:00:02Z', comment_id: null, queued: false },
    { id: 4, kind: 'reply', text: 'Done: **retries** added.', created_at: '2026-11-23T10:00:03Z', comment_id: null, queued: false },
    { id: 5, kind: 'user', text: 'Also cap the delay', created_at: '2026-11-23T10:00:04Z', comment_id: null, queued: true },
    { id: 6, kind: 'system', text: 'Stopped by Pablo', created_at: '2026-11-23T10:00:05Z', comment_id: null, queued: false },
    { id: 7, kind: 'error', text: 'usage limit', created_at: '2026-11-23T10:00:06Z', comment_id: null, queued: false },
  ],
}

const answers: Record<string, unknown> = {
  'GET /api/bootstrap': boot,
  'GET /api/tickets': { tickets: [ticket] },
  'GET /api/tickets/1': ticketDetail,
  'GET /api/tasks?status=all': { tasks },
  'GET /api/tasks/3': taskDetail,
  'GET /api/activity': {
    items: [{ comment: comments[1], ticket: { id: 1, key: 'AH-1', title: 'Add retries' }, ai_user_id: 'engineer', task_id: 3 }],
    unseen: 2,
  },
}

const calls: Array<{ method: string; url: string; contentType: string | null }> = []

beforeAll(async () => {
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const headers = (init?.headers ?? {}) as Record<string, string>
    calls.push({ method, url, contentType: headers['Content-Type'] ?? null })
    const body = answers[`${method} ${url}`]
    if (body === undefined) return new Response(JSON.stringify({ message: 'not found' }), { status: 404 })
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  await Promise.all([loadBoot(), loadTickets(), loadTasks(), loadActivity()])
})

const text = (html: string) => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')

describe('views rendered from contract-shaped data', () => {
  it('loads every list through relative URLs', () => {
    expect(getState().boot?.users).toHaveLength(4)
    expect(getState().tickets).toHaveLength(1)
    expect(getState().tasks).toHaveLength(3)
    expect(getState().unseen).toBe(2)
    expect(calls.every((c) => c.url.startsWith('/api/'))).toBe(true)
  })

  it('shows the header with brand, tabs, counters and Settings', () => {
    const page = text(renderToStaticMarkup(<App />))
    expect(page).toContain('AgentHub')
    expect(page).toMatch(/Board/)
    expect(page).toMatch(/Tasks 1/) // one task waiting on user
    expect(page).toMatch(/Activity 2/) // two unseen AI comments
    expect(page).toContain('Settings')
  })

  it('shows the board columns and the card', () => {
    const page = text(renderToStaticMarkup(<Board />))
    for (const name of ['Backlog', 'To do', 'In progress', 'In review', 'Done']) expect(page).toContain(name)
    expect(page).toContain('AgentHub board')
    expect(page).toContain('AH-1')
    expect(page).toContain('Running')
    expect(page).toContain('Add a card')
    expect(page).not.toContain('Payments API')
  })

  it('shows the Tasks page with filters, counts, timer and Stop', () => {
    const page = text(renderToStaticMarkup(<TasksPage />))
    for (const f of ['All', 'Running', 'Waiting on user', 'Done', 'Archived', 'New task']) expect(page).toContain(f)
    expect(page).toContain('12.3k session')
    expect(page).toContain('3k harness')
    expect(page).toContain('Stop')
    expect(page).toMatch(/0:4[2-4]/)
    expect(page).not.toContain('Check the deploy') // archived: only under its filter
    expect(page).toContain('Not logged in') // status_reason of the waiting task
  })

  it('shows the ticket dialog with delivery lines, totals and the Tasks block', async () => {
    openTicket(1)
    await loadTicketDetail()
    const html = renderToStaticMarkup(<TicketDialog />)
    const page = text(html)
    expect(page).toContain('Sent to Engineer · Started a task for DevOps')
    expect(page).toContain('Sent to no task')
    expect(page).toContain('13.3k session')
    expect(page).toContain('Check the deploy') // archived task listed in the ticket
    expect(page).toContain('git@github.com:owner/AgentHub.git')
    expect(page).toContain('Tag someone')
    expect(html).toContain('class="ah-mention"')
    expect(html).toContain('href="https://example.com/spec" target="_blank"')
  })

  it('shows the task dialog with every kind of chat line', async () => {
    openTask(3)
    await loadTaskDetail()
    const html = renderToStaticMarkup(<TaskDialog />)
    const page = text(html)
    for (const s of ['Stop', 'View ticket', 'queued', 'Stopped by Pablo', 'usage limit', 'Read src/sender.py', 'retries_1']) {
      expect(page).toContain(s)
    }
    expect(html).toContain('<strong>retries</strong>')
    expect(page).not.toContain('Archive')
  })

  it('shows the Activity entries with a reply box, and Settings', () => {
    const activity = text(renderToStaticMarkup(<ActivityPage />))
    expect(activity).toContain('AH-1')
    expect(activity).toContain('Tag someone')
    expect(activity).toContain('Post')
    const settings = text(renderToStaticMarkup(<SettingsPage />))
    expect(settings).toContain('You are the engineer.')
    expect(settings).toContain('Logged in')
  })
})

describe('voice input controls', () => {
  const fields = async () => {
    openTicket(1)
    await loadTicketDetail()
    openTask(3)
    await loadTaskDetail()
    return [
      renderToStaticMarkup(<TicketDialog />),
      renderToStaticMarkup(<ActivityPage />),
      renderToStaticMarkup(<TaskDialog />),
      renderToStaticMarkup(<AddTicketForm stageId="backlog" onClose={() => {}} />),
      renderToStaticMarkup(<NewTaskForm onClose={() => {}} />),
    ]
  }

  it('shows a microphone control at each field when the browser offers speech recognition', async () => {
    vi.stubGlobal('SpeechRecognition', class {})
    try {
      for (const html of await fields()) expect(html).toContain('aria-label="Start voice input"')
    } finally {
      vi.stubGlobal('SpeechRecognition', undefined)
    }
  })

  it('shows no microphone control when the browser offers none', async () => {
    for (const html of await fields()) expect(html).not.toContain('voice input')
  })
})

describe('card description fields', () => {
  const textareas = (html: string) => html.match(/<textarea[^>]*>/g) ?? []
  const descriptionTag = (html: string) => html.match(/<textarea[^>]*aria-label="Description"[^>]*>/)?.[0] ?? ''

  it('opens "Add a card" as a 640px dialog naming the stage, with a 6-line description that follows its text', () => {
    const html = renderToStaticMarkup(<AddTicketForm stageId="backlog" onClose={() => {}} />)
    const tag = descriptionTag(html)
    for (const s of ['rows="6"', 'min-height:142px', 'field-sizing:content', 'max-height:60vh', 'placeholder="Description (optional)"']) {
      expect(tag).toContain(s)
    }
    expect(html).toMatch(/role="dialog"[^>]*max-width:640px/)
    expect(text(html)).toContain('Backlog')
  })

  it('gives the card dialog\'s editor settings 10 lines and the microphone', () => {
    const voice: Dictation = { supported: true, listening: false, error: null, toggle() {}, cancel() {} }
    const html = renderToStaticMarkup(
      <DescriptionField value="Retry failed deliveries." onChange={() => {}} minRows={10} voice={voice} />,
    )
    const tag = descriptionTag(html)
    expect(tag).toContain('rows="10"')
    expect(tag).toContain('min-height:222px')
    expect(html).toContain('Retry failed deliveries.')
    expect(html).toContain('aria-label="Start voice input"')
  })

  it('leaves the other text fields and the board as they were', async () => {
    openTicket(1)
    await loadTicketDetail()
    const newTask = renderToStaticMarkup(<NewTaskForm onClose={() => {}} />)
    const settings = renderToStaticMarkup(<SettingsPage />)
    const ticketDialog = renderToStaticMarkup(<TicketDialog />) // read mode: the comment box is its only field
    expect(textareas(newTask)).toEqual([expect.stringContaining('rows="5"')])
    expect(textareas(settings).length).toBeGreaterThan(0)
    for (const tag of textareas(settings)) expect(tag).toContain('rows="8"')
    expect(textareas(ticketDialog)).toEqual([expect.stringContaining('rows="3"')])
    for (const html of [newTask, settings, ticketDialog]) expect(html).not.toContain('field-sizing')
    expect(renderToStaticMarkup(<Board />)).not.toContain('role="dialog"')
  })
})
