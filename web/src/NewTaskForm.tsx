import { useId, useState, type FormEvent } from 'react'
import { api, errorMessage } from './api'
import { applyTaskDetail, loadTasks, openTask, useAppState } from './store'
import { color, font, textarea } from './theme'
import { Button, CloseButton, Dialog, ErrorText, FieldLabel, Select } from './ui'

/** "New task": a task without a ticket, for an AI user Pablo must pick. */
export default function NewTaskForm({ onClose }: { onClose: () => void }) {
  const { boot } = useAppState()
  const uid = useId()
  const [aiUser, setAiUser] = useState('')
  const [model, setModel] = useState(boot?.default_model ?? boot?.models[0] ?? '')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!boot) return null

  const aiUsers = boot.users.filter((u) => u.kind === 'ai')

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (!aiUser || busy) return
    if (!message.trim()) {
      setError('Write the first message for the task.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const task = await api.createTask({ ai_user_id: aiUser, message: message.trim(), model })
      applyTaskDetail(task)
      void loadTasks()
      onClose()
      openTask(task.id)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Dialog label="New task" onClose={() => !busy && onClose()} maxWidth={560}>
      <form onSubmit={(e) => void submit(e)} style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '10px 10px 24px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontFamily: font.display, fontSize: 21, lineHeight: '28px', fontWeight: 700 }}>New task</h2>
          <span style={{ marginLeft: 'auto' }}>
            <CloseButton label="Close new task" onClick={onClose} />
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingRight: 14 }}>
          <p style={{ margin: 0, color: color.muted, fontSize: 13 }}>
            A task on its own, attached to no ticket. The AI user starts working on your message right away.
          </p>
          <FieldLabel htmlFor={`${uid}-user`}>AI user</FieldLabel>
          <Select
            id={`${uid}-user`}
            value={aiUser}
            onChange={setAiUser}
            disabled={busy}
            placeholder="Choose an AI user"
            options={aiUsers.map((u) => ({ value: u.id, label: u.name }))}
          />
          <FieldLabel htmlFor={`${uid}-model`}>Model</FieldLabel>
          <Select
            id={`${uid}-model`}
            value={model}
            onChange={setModel}
            disabled={busy}
            options={boot.models.map((m) => ({ value: m, label: m }))}
          />
          <FieldLabel htmlFor={`${uid}-message`}>Message</FieldLabel>
          <textarea
            id={`${uid}-message`}
            rows={5}
            value={message}
            disabled={busy}
            placeholder="What should the AI user do?"
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                void submit()
              }
            }}
            style={textarea}
          />
          {error && (
            <ErrorText>{error}</ErrorText>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <Button kind="primary" type="submit" disabled={!aiUser || busy} style={{ minHeight: 44 }}>
              {busy ? 'Starting…' : 'Start task'}
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
