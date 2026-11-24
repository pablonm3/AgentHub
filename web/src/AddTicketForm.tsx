import { useId, useState, type FormEvent } from 'react'
import { api, errorBody, errorMessage, type NewTicket } from './api'
import DescriptionField from './DescriptionField'
import { repoWebUrl } from './lib/format'
import { applyTicketDetail, notify, refresh, useAppState } from './store'
import { color, font, input } from './theme'
import { Button, CloseButton, Dialog, ErrorText, FieldLabel, Select } from './ui'
import { useDictation } from './voice'

const NEW_PROJECT = '__new__'
const NO_PROJECT = '__none__'

interface NewProjectError {
  message: string
  createdRepo: string | null
}

/** "Add a card" to one board stage, in a dialog: title, description, assignee, model and project. */
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
      const name = projectName.trim()
      if (!name) {
        setNewProjectError({ message: 'Give the new project a name.', createdRepo: null })
        return
      }
      const url = repoUrl.trim()
      body = { ...base, new_project: url ? { name, repo_url: url } : { name } }
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
  const shownName = projectName.trim() || 'the project name'
  const stageName = boot.stages.find((g) => g.id === stageId)?.name ?? stageId
  // Escape, the backdrop and the close button land here; nothing closes while a submit is in flight.
  const close = () => {
    if (!busy) onClose()
  }

  return (
    <Dialog label="Add a card" onClose={close} maxWidth={640}>
      <form onSubmit={(e) => void submit(e)} style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '10px 10px 24px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h2 style={{ margin: 0, fontFamily: font.display, fontSize: 21, lineHeight: '28px', fontWeight: 700 }}>Add a card</h2>
          <span style={{ color: color.muted, fontSize: 13 }}>{stageName}</span>
          <span style={{ marginLeft: 'auto' }}>
            <CloseButton label="Close add a card" onClick={close} />
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingRight: 14 }}>
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
          <DescriptionField
            value={description}
            onChange={setDescription}
            voice={voice}
            minRows={6}
            disabled={busy}
            placeholder="Description (optional)"
          />
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
                value={projectName}
                disabled={busy}
                onChange={(e) => setProjectName(e.target.value)}
                style={input}
              />
              <FieldLabel htmlFor={`${uid}-purl`}>Repo URL (optional)</FieldLabel>
              <input
                id={`${uid}-purl`}
                type="text"
                autoComplete="off"
                placeholder="git@github.com:owner/repo.git"
                value={repoUrl}
                disabled={busy}
                onChange={(e) => setRepoUrl(e.target.value)}
                style={input}
              />
              <p style={{ margin: 0, color: color.muted, fontSize: 12, lineHeight: '17px' }}>
                Leave the URL empty to create a private GitHub repository named <strong>{shownName}</strong> on the
                account <code style={{ fontFamily: font.mono }}>gh</code> is logged in with.
              </p>
              {newProjectError && (
                <div role="alert" style={{ color: color.errorInk, fontSize: 13, lineHeight: '18px', overflowWrap: 'anywhere' }}>
                  <p style={{ margin: 0 }}>{newProjectError.message}</p>
                  {newProjectError.createdRepo && (
                    <p style={{ margin: '4px 0 0' }}>
                      Repository created:{' '}
                      <a href={repoWebUrl(newProjectError.createdRepo) ?? newProjectError.createdRepo} target="_blank" rel="noopener noreferrer">
                        {newProjectError.createdRepo}
                      </a>
                    </p>
                  )}
                </div>
              )}
            </div>
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
        </div>
      </form>
    </Dialog>
  )
}
