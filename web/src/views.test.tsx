// Renders every view from answers shaped like the API contract, through the store's own
// loaders, to catch render errors and check the labels the UI must show.

import { renderToStaticMarkup } from 'react-dom/server'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import ActivityPage from './ActivityPage'
import AddTicketForm, { NewProjectFields } from './AddTicketForm'
import App from './App'
import Board from './Board'
import DescriptionField from './DescriptionField'
import NewTaskForm from './NewTaskForm'
import SettingsPage from './SettingsPage'
import TaskDialog from './TaskDialog'
import TasksPage from './TasksPage'
import TicketDialog from './TicketDialog'
import type { Bootstrap, ChatEvent, Comment, GithubStatus, Task, TaskDetail, TaskLink, Ticket, TicketDetail } from './api'
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
  refresh,
} from './store'
import type { Dictation } from './voice'

const NOW = Date.now()
const RESETS = Math.floor(NOW / 1000) + 4 * 86400

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
  github: { can_create: true, reason: null },
  usage: [
    { limit: 'seven_day', used: 0.22, resets_at: RESETS, reached: false, read_at: new Date(NOW - 5 * 60_000).toISOString() },
    {
      limit: 'seven_day_overage_included',
      used: 0.37,
      resets_at: RESETS,
      reached: false,
      read_at: new Date(NOW - 2 * 3_600_000).toISOString(),
    },
  ],
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
    parent: null,
    children: [],
    waiting_on: null,
    created_at: '2026-11-23T10:00:00Z',
    updated_at: '2026-11-23T10:05:00Z',
    ...over,
  }
}

const link = (t: Task): TaskLink => ({
  id: t.id,
  ai_user_id: t.ai_user_id,
  title: t.title,
  display_title: t.display_title,
  status: t.status,
  waiting_on: t.waiting_on,
})

// Task 6 is a child of task 3: DevOps works for the Engineer and waits on its answer.
const parentTask = task({ id: 3 })
const childTask = task({
  id: 6,
  ai_user_id: 'devops',
  origin: 'ai_user',
  title: 'Profile the retry queue',
  display_title: 'Profile the retry queue',
  status: 'waiting_on_user',
  running_since: null,
  harness_runs: [],
  parent: link(parentTask),
  waiting_on: { task_id: 3, ai_user_id: 'engineer' },
})
parentTask.children = [link(childTask)]

const tasks: Task[] = [
  parentTask,
  task({ id: 4, ai_user_id: 'devops', status: 'archived', title: null, display_title: 'Check the deploy', running_since: null, session_tokens: 950, harness_tokens: 0, harness_runs: [] }),
  task({ id: 5, ticket_id: null, ticket_key: null, ticket_title: null, origin: 'manual', ai_user_id: 'data_scientist', status: 'waiting_on_user', running_since: null, status_reason: 'Not logged in' }),
  childTask,
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
  task_waiting_on: null,
  created_at: '2026-11-23T10:00:00Z',
  updated_at: '2026-11-23T10:05:00Z',
}

const plain = { child_task: null, in_activity: 1 }
const comments: Comment[] = [
  { id: 10, ticket_id: 1, author_id: 'pablo', body: 'Please look, @Engineer and @DevOps', task_id: null, reply_to_id: null, created_at: '2026-11-23T10:01:00Z', delivered_to: [{ task_id: 3, ai_user_id: 'engineer' }], started: [{ task_id: 4, ai_user_id: 'devops' }], ...plain },
  { id: 11, ticket_id: 1, author_id: 'engineer', body: 'Done, see [the report](/reports/3/report.html)', task_id: 3, reply_to_id: null, created_at: '2026-11-23T10:02:00Z', delivered_to: [], started: [], ...plain },
  { id: 12, ticket_id: 1, author_id: 'pablo', body: 'Thanks', task_id: null, reply_to_id: 11, created_at: '2026-11-23T10:03:00Z', delivered_to: [], started: [], ...plain },
  { id: 13, ticket_id: 1, author_id: 'engineer', body: 'Created a task for DevOps:\n\n> Profile the retry queue', task_id: 3, reply_to_id: null, created_at: '2026-11-23T10:04:00Z', delivered_to: [], started: [], child_task: link(childTask), in_activity: 1 },
]

const ticketDetail: TicketDetail = {
  ...ticket,
  comments,
  tasks: [tasks[0], tasks[1], childTask],
  session_tokens: 13_295,
  harness_tokens: 3000,
  project_info: boot.projects[0],
}

const line = (id: number, kind: ChatEvent['kind'], text: string, over: Partial<ChatEvent> = {}): ChatEvent => ({
  id,
  kind,
  text,
  created_at: `2026-11-23T10:00:0${id}Z`,
  comment_id: null,
  queued: false,
  from_task: null,
  ...over,
})

const taskDetail: TaskDetail = {
  ...tasks[0],
  events: [
    line(1, 'notice', 'Ticket AH-1: Add retries'),
    line(2, 'tool', 'Read src/sender.py'),
    line(3, 'assistant', 'Looking at the sender.'),
    line(4, 'reply', 'Done: **retries** added.'),
    line(5, 'user', 'Also cap the delay', { queued: true }),
    line(6, 'system', 'Stopped by Pablo'),
    line(7, 'error', 'usage limit'),
    line(8, 'ai_user', 'Which queue do you mean?', { from_task: { task_id: 6, ai_user_id: 'devops' } }),
  ],
}

const childDetail: TaskDetail = {
  ...childTask,
  events: [
    line(1, 'ai_user', 'Profile the retry queue', { from_task: { task_id: 3, ai_user_id: 'engineer' } }),
    line(2, 'reply', 'Which queue do you mean?'),
  ],
}

const answers: Record<string, unknown> = {
  'GET /api/bootstrap': boot,
  'GET /api/tickets': { tickets: [ticket] },
  'GET /api/tickets/1': ticketDetail,
  'GET /api/tasks?status=all': { tasks },
  'GET /api/tasks/3': taskDetail,
  'GET /api/tasks/6': childDetail,
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

const text = (html: string) =>
  html
    .replace(/<[^>]+>/g, ' ')
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')

/** The header's text, as the page shows it. */
const headerText = () => text(/<header[\s\S]*?<\/header>/.exec(renderToStaticMarkup(<App />))?.[0] ?? '')

/** Serve and load a bootstrap that differs from the fixture in `over`. */
async function applyBoot(over: Partial<Bootstrap>): Promise<void> {
  answers['GET /api/bootstrap'] = { ...boot, ...over }
  await loadBoot()
}

describe('views rendered from contract-shaped data', () => {
  it('loads every list through relative URLs', () => {
    expect(getState().boot?.users).toHaveLength(4)
    expect(getState().tickets).toHaveLength(1)
    expect(getState().tasks).toHaveLength(4)
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
    expect(page).toContain('Usage left')
    expect(page).toMatch(/Week\s+78%.*Fable week\s+63%/)
    expect(page).toMatch(/Week\s+78%\s+resets\s.+?·\s+read\s+5 min ago/)
    expect(page).toMatch(/Fable week\s+63%\s+resets\s.+?·\s+read\s+2 h ago/)
  })

  it('shows in the header that the usage left is not known when no figure is', async () => {
    try {
      await applyBoot({ usage: [] })
      const header = headerText()
      expect(header).toContain('Usage left: not known')
      expect(header).not.toContain('%')
      expect(header).not.toContain('resets')
    } finally {
      await applyBoot({})
    }
  })

  it('shows a reached limit in the header before the weekly figures', async () => {
    const fiveHour = { limit: 'five_hour', used: null, resets_at: RESETS - 86400, reached: true, read_at: new Date(NOW).toISOString() }
    try {
      await applyBoot({ usage: [...boot.usage, fiveHour] })
      expect(headerText()).toMatch(/5 h limit reached\s+resets\s.+?·\s+read\s+just now.*Week\s+78%/)
    } finally {
      await applyBoot({})
    }
  })

  it('reloads the figures when the server publishes topic usage', async () => {
    const newer = [{ ...boot.usage[0], used: 0.24, read_at: new Date(NOW).toISOString() }]
    try {
      answers['GET /api/bootstrap'] = { ...boot, usage: newer }
      refresh('usage')
      await vi.waitFor(() => expect(getState().boot?.usage).toEqual(newer))
      expect(headerText()).toMatch(/Week\s+76%/)
    } finally {
      await applyBoot({})
    }
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

describe('parent and child tasks', () => {
  it('shows a child task waiting on its parent, and the parent with its children, on the Tasks page', () => {
    const page = text(renderToStaticMarkup(<TasksPage />))
    expect(page).toContain(`AH-1 · DevOps · child of Engineer's task "Retry the webhook sender"`)
    expect(page).toContain('Waiting on Engineer Profile the retry queue') // the child's own pill
    expect(page).toContain('Child tasks Waiting on Engineer DevOps') // the parent's row
    // waiting on an AI user: under All only, not under Running or Waiting on user
    expect(page).toMatch(/All 3 /)
    expect(page).toMatch(/Running 1 /)
    expect(page).toMatch(/Waiting on user 1 /)
  })

  it('leaves a task waiting on an AI user out of the header count and shows it on the card', async () => {
    expect(headerText()).toMatch(/Tasks 1(?!\d)/)
    const saved = answers['GET /api/tickets']
    try {
      answers['GET /api/tickets'] = { tickets: [{ ...ticket, task_status: 'waiting_on_user', task_waiting_on: 'engineer' }] }
      await loadTickets()
      const card = text(renderToStaticMarkup(<Board />))
      expect(card).toContain('Waiting on Engineer')
      expect(card).not.toContain('Waiting on user')
    } finally {
      answers['GET /api/tickets'] = saved
      await loadTickets()
    }
  })

  it('lists the children in the parent task dialog and an AI user message as theirs', async () => {
    openTask(3)
    await loadTaskDetail()
    const page = text(renderToStaticMarkup(<TaskDialog />))
    expect(page).toContain('Child tasks Waiting on Engineer DevOps · Profile the retry queue')
    expect(page).toContain('DevOps · task 6')
    expect(page).toContain('Which queue do you mean?')
    expect(page).not.toContain('Child of')
  })

  it('shows the parent in the child task dialog and waits on the asker by name', async () => {
    openTask(6)
    await loadTaskDetail()
    const page = text(renderToStaticMarkup(<TaskDialog />))
    expect(page).toContain('Waiting on Engineer AH-1 · DevOps')
    expect(page).toContain('Child of Engineer · Retry the webhook sender')
    expect(page).toContain('Engineer · task 3')
    expect(page).toContain('waiting for Engineer')
    expect(page).not.toContain('waiting for your reply')
  })

  it('shows the child in the ticket dialog Tasks block and under the comment that announces it', async () => {
    openTicket(1)
    await loadTicketDetail()
    const page = text(renderToStaticMarkup(<TicketDialog />))
    expect(page).toContain("Child of Engineer's task")
    expect(page).toContain("Created a task for DevOps: Profile the retry queue Waiting on Engineer Open DevOps's task Open task")
  })

  it('shows a new status of the child everywhere after the tasks topic, without a new mount', async () => {
    const keys = ['GET /api/tasks?status=all', 'GET /api/tasks/3', 'GET /api/tasks/6', 'GET /api/tickets/1']
    const saved = keys.map((k) => answers[k])
    const done = { ...childTask, status: 'done' as const, waiting_on: null }
    const doneLink = link(done)
    const parentNow = { ...parentTask, children: [doneLink] }
    try {
      answers['GET /api/tasks?status=all'] = { tasks: [parentNow, tasks[1], tasks[2], done] }
      answers['GET /api/tasks/3'] = { ...taskDetail, children: [doneLink] }
      answers['GET /api/tasks/6'] = { ...childDetail, ...done }
      answers['GET /api/tickets/1'] = {
        ...ticketDetail,
        tasks: [parentNow, tasks[1], done],
        comments: comments.map((c) => (c.child_task ? { ...c, child_task: doneLink } : c)),
      }
      openTicket(1)
      openTask(3)
      refresh('tasks')
      await vi.waitFor(() => {
        expect(getState().taskDetail?.children[0]?.status).toBe('done')
        expect(getState().ticketDetail?.tasks[2]?.status).toBe('done')
        expect(getState().tasks.find((t) => t.id === 6)?.status).toBe('done')
      })
      expect(text(renderToStaticMarkup(<TaskDialog />))).toContain('Child tasks Done DevOps · Profile the retry queue')
      expect(text(renderToStaticMarkup(<TasksPage />))).toContain('Child tasks Done DevOps')
      const ticketPage = text(renderToStaticMarkup(<TicketDialog />))
      expect(ticketPage).toContain("Profile the retry queue Done Open DevOps's task")
      expect(ticketPage).not.toContain('Waiting on Engineer')
    } finally {
      keys.forEach((k, i) => (answers[k] = saved[i]))
      await Promise.all([loadTasks(), loadTaskDetail(), loadTicketDetail()])
    }
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

describe('the New project block', () => {
  const render = (github: GithubStatus | undefined, error: { message: string; createdRepo: string | null } | null = null) =>
    renderToStaticMarkup(
      <NewProjectFields
        github={github}
        name="proj"
        repoUrl=""
        busy={false}
        error={error}
        onName={() => {}}
        onRepoUrl={() => {}}
      />,
    )
  const labels = (html: string) => (html.match(/<label[^>]*>.*?<\/label>/g) ?? []).map((l) => text(l).trim())

  it('offers to create the repository when this machine can', () => {
    const html = render({ can_create: true, reason: null })
    expect(labels(html)).toEqual(['Project name', 'Repo URL (optional)'])
    expect(text(html)).toContain('Leave the URL empty to create a private GitHub repository named proj')
    expect(html).not.toContain('aria-required')
  })

  it('requires the URL and says how to install gh when it is not installed', () => {
    const html = render({ can_create: false, reason: 'not_installed' })
    const shown = text(html)
    expect(labels(html)).toEqual(['Project name', 'Repo URL'])
    expect(shown).not.toMatch(/optional/i)
    expect(shown).not.toContain('Leave the URL empty')
    expect(shown).toContain('gh is not installed on the machine that runs AgentHub')
    expect(shown).toContain('Installing it and running gh auth login there lets this form create repositories')
    expect(html).toContain('aria-required="true"')
  })

  it('requires the URL and says how to log in when gh is not logged in', () => {
    const html = render({ can_create: false, reason: 'not_logged_in' })
    const shown = text(html)
    expect(labels(html)).toEqual(['Project name', 'Repo URL'])
    expect(shown).not.toContain('Leave the URL empty')
    expect(shown).toContain('gh is not logged in on the machine that runs AgentHub')
    expect(shown).toContain('Running gh auth login there lets this form create repositories')
  })

  it('requires the URL when gh did not answer or the server did not say', () => {
    for (const github of [{ can_create: false, reason: 'unknown' } as const, undefined]) {
      const html = render(github)
      expect(labels(html)).toEqual(['Project name', 'Repo URL'])
      expect(text(html)).toContain('gh did not answer on the machine that runs AgentHub')
    }
  })

  it('shows the error in the block', () => {
    const html = render({ can_create: false, reason: 'not_installed' }, { message: 'Enter the repo URL: this machine cannot create a GitHub repository.', createdRepo: null })
    expect(html).toContain('role="alert"')
    expect(text(html)).toContain('Enter the repo URL: this machine cannot create a GitHub repository.')
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
