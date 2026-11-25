import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react'
import { api, errorBody, errorMessage, type GithubStatus, type NewTicket } from './api'
import { repoWebUrl } from './lib/format'
import { canCreateRepo, newProjectInput } from './lib/newProject'
import { applyTicketDetail, loadBoot, notify, refresh, useAppState } from './store'
import { color, font, input, textarea } from './theme'
import { Button, ErrorText, FieldLabel, Select } from './ui'
import { MicButton, useDictation } from './voice'

const NEW_PROJECT = '__new__'
const NO_PROJECT = '__none__'

export interface NewProjectError {
  message: string
  createdRepo: string | null
}

/** "Add a card" in one board column: title, description, assignee, model and project. */
export default function AddTicketForm({ stageId, onClose }: { stageId: string; onClose: () => void }) {
  const { boot } = useAppState()
  const uid = useId()
  const users = boot?.users ?? []
  const human = users.find((u) => u.id === 'pablo') ?? users.find((u) => u.kind === 'human')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [assignee, setAssignee] = useState(human?.id ?? users[0]?.id ?? '')
  const [model, setModel] = useState(boot?.default_model ?? boot?.models[0] ?? '')
  const [project, setProject] = useState(NO_PROJECT)
  const [projectName, setProjectName] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [newProjectError, setNewProjectError] = useState<NewProjectError | null>(null)
  const voice = useDictation(setDescription)

  // What `gh` can do may have changed since the last poll, which stops while the tab is hidden.
  useEffect(() => {
    void loadBoot()
  }, [])

  if (!boot) return null
  const isNew = project === NEW_PROJECT

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (busy) return
    setFormError(null)
    setNewProjectError(null)
    const base = { title: title.trim(), description: description.trim(), stage: stageId, assignee_id: assignee, model }
    if (!base.title) {
      setFormError('Give the card a title.')
      return
    }
    let body: NewTicket
    if (isNew) {
      const checked = newProjectInput(projectName, repoUrl, canCreateRepo(boot.github))
      if (!checked.ok) {
        setNewProjectError({ message: checked.error, createdRepo: null })
        return
      }
      body = { ...base, new_project: checked.new_project }
    } else {
      body = { ...base, project: project === NO_PROJECT ? null : project }
    }
    voice.cancel()
    setBusy(true)
    try {
      const detail = await api.createTicket(body)
      applyTicketDetail(detail)
      if (detail.warning) notify('warning', detail.warning)
      refresh('tickets', 'tasks', ...(isNew ? (['projects'] as const) : []))
      onClose()
    } catch (err) {
      if (isNew) {
        const created = errorBody(err).created_repo
        setNewProjectError({ message: errorMessage(err), createdRepo: typeof created === 'string' && created ? created : null })
      } else {
        setFormError(errorMessage(err))
      }
    } finally {
      setBusy(false)
    }
  }

  const options = [
    ...boot.projects.map((p) => ({ value: p.name, label: p.name })),
    { value: NEW_PROJECT, label: 'New project' },
    { value: NO_PROJECT, label: 'No project' },
  ]

  return (
    <form
      onSubmit={(e) => void submit(e)}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && !busy) onClose()
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
    >
      <input
        type="text"
        aria-label="Card title"
        placeholder="Card title"
        autoFocus
        autoComplete="off"
        value={title}
        disabled={busy}
        onChange={(e) => setTitle(e.target.value)}
        style={{ ...input, height: 44 }}
      />
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <textarea
          aria-label="Description"
          placeholder="Description (optional)"
          rows={3}
          value={description}
          disabled={busy}
          onChange={(e) => setDescription(e.target.value)}
          style={{ ...textarea, flex: '1 1 0', minWidth: 0 }}
        />
        <MicButton voice={voice} disabled={busy} />
      </div>
      {voice.error && <ErrorText>{voice.error}</ErrorText>}
      <FieldLabel htmlFor={`${uid}-assignee`}>Assignee</FieldLabel>
      <Select
        id={`${uid}-assignee`}
        value={assignee}
        onChange={setAssignee}
        disabled={busy}
        options={users.map((u) => ({ value: u.id, label: u.name }))}
      />
      <FieldLabel htmlFor={`${uid}-model`}>Model</FieldLabel>
      <Select
        id={`${uid}-model`}
        value={model}
        onChange={setModel}
        disabled={busy}
        options={boot.models.map((m) => ({ value: m, label: m }))}
      />
      <FieldLabel htmlFor={`${uid}-project`}>Project</FieldLabel>
      <Select
        id={`${uid}-project`}
        value={project}
        onChange={(v) => {
          setProject(v)
          setNewProjectError(null)
        }}
        disabled={busy}
        options={options}
      />
      {isNew && (
        <NewProjectFields
          github={boot.github}
          name={projectName}
          repoUrl={repoUrl}
          busy={busy}
          error={newProjectError}
          onName={setProjectName}
          onRepoUrl={setRepoUrl}
        />
      )}
      {formError && (
        <ErrorText>{formError}</ErrorText>
      )}
      <div style={{ display: 'flex', gap: 8 }}>
        <Button kind="primary" type="submit" disabled={busy} style={{ minHeight: 44 }}>
          {busy ? (isNew ? 'Registering project…' : 'Adding…') : 'Add card'}
        </Button>
        <Button kind="ghost" onClick={onClose} disabled={busy} style={{ minHeight: 44 }}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

const gh = <code style={{ fontFamily: font.mono }}>gh</code>
const ghLogin = <code style={{ fontFamily: font.mono }}>gh auth login</code>

/** Under the repo URL: what an empty URL does, or why this machine cannot create a repository. */
function repoUrlHint(github: GithubStatus | undefined, shownName: string): ReactNode {
  if (canCreateRepo(github)) {
    return (
      <>
        Leave the URL empty to create a private GitHub repository named <strong>{shownName}</strong> on the
        account {gh} is logged in with.
      </>
    )
  }
  if (github?.reason === 'not_installed') {
    return (
      <>
        {gh} is not installed on the machine that runs AgentHub. Installing it and running {ghLogin} there lets
        this form create repositories (restart AgentHub if the form still says this).
      </>
    )
  }
  if (github?.reason === 'not_logged_in') {
    return (
      <>
        {gh} is not logged in on the machine that runs AgentHub. Running {ghLogin} there lets this form create
        repositories.
      </>
    )
  }
  return <>{gh} did not answer on the machine that runs AgentHub, so this form cannot create a repository right now.</>
}

/** The "New project" block: name, repo URL (required when this machine cannot create a repository), hint, error. */
export function NewProjectFields({
  github,
  name,
  repoUrl,
  busy,
  error,
  onName,
  onRepoUrl,
}: {
  github: GithubStatus | undefined
  name: string
  repoUrl: string
  busy: boolean
  error: NewProjectError | null
  onName: (v: string) => void
  onRepoUrl: (v: string) => void
}) {
  const uid = useId()
  const urlRequired = !canCreateRepo(github)
  const shownName = name.trim() || 'the project name'
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        padding: 10,
        borderRadius: 10,
        background: color.surface,
        border: `1px solid ${color.line}`,
      }}
    >
      <FieldLabel htmlFor={`${uid}-pname`}>Project name</FieldLabel>
      <input
        id={`${uid}-pname`}
        type="text"
        autoComplete="off"
        value={name}
        disabled={busy}
        onChange={(e) => onName(e.target.value)}
        style={input}
      />
      <FieldLabel htmlFor={`${uid}-purl`}>{urlRequired ? 'Repo URL' : 'Repo URL (optional)'}</FieldLabel>
      <input
        id={`${uid}-purl`}
        type="text"
        autoComplete="off"
        placeholder="git@github.com:owner/repo.git"
        aria-required={urlRequired || undefined}
        value={repoUrl}
        disabled={busy}
        onChange={(e) => onRepoUrl(e.target.value)}
        style={input}
      />
      <p style={{ margin: 0, color: color.muted, fontSize: 12, lineHeight: '17px' }}>{repoUrlHint(github, shownName)}</p>
      {error && (
        <div role="alert" style={{ color: color.errorInk, fontSize: 13, lineHeight: '18px', overflowWrap: 'anywhere' }}>
          <p style={{ margin: 0 }}>{error.message}</p>
          {error.createdRepo && (
            <p style={{ margin: '4px 0 0' }}>
              Repository created:{' '}
              <a href={repoWebUrl(error.createdRepo) ?? error.createdRepo} target="_blank" rel="noopener noreferrer">
                {error.createdRepo}
              </a>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
