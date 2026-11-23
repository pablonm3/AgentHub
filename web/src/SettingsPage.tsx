import { useEffect, useState, type ReactNode } from 'react'
import { api, errorMessage, type Login, type User } from './api'
import { applyBoot, applyUser, useAppState } from './store'
import { color, font, pageTitle, sectionHeading, textarea } from './theme'
import { Avatar, Button, Select } from './ui'

export default function SettingsPage() {
  const { boot } = useAppState()
  if (!boot) return null
  const aiUsers = boot.users.filter((u) => u.kind === 'ai')

  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 28,
        width: '100%',
        maxWidth: 920,
        margin: '0 auto',
        padding: '24px 24px 40px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <h1 style={pageTitle}>Settings</h1>
        <p style={{ margin: 0, color: color.muted }}>The default model, the AI users' role prompts and the Claude login.</p>
      </div>
      <DefaultModel models={boot.models} value={boot.default_model} />
      <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <h2 style={sectionHeading}>Role prompts</h2>
        <p style={{ margin: 0, color: color.muted, fontSize: 13 }}>
          Each AI user's prompt is used for every task started for it after you save.
        </p>
        {aiUsers.map((u) => (
          <PromptEditor key={u.id} user={u} />
        ))}
      </section>
      <LoginStatus fallback={boot.login} />
    </main>
  )
}

function Card({ children }: { children: ReactNode }) {
  return (
    <div
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
      {children}
    </div>
  )
}

function DefaultModel({ models, value }: { models: string[]; value: string }) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const change = async (next: string) => {
    if (next === value) return
    setBusy(true)
    setNote(null)
    try {
      const saved = await api.updateSettings(next)
      applyBoot({ default_model: saved.default_model })
      setNote({ ok: true, text: 'Saved. New tickets and tasks preselect this model.' })
    } catch (err) {
      setNote({ ok: false, text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h2 style={sectionHeading}>Default model</h2>
      <Card>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>
          <Select
            ariaLabel="Default model"
            value={value}
            disabled={busy}
            onChange={(v) => void change(v)}
            options={models.map((m) => ({ value: m, label: m }))}
            style={{ width: 220 }}
          />
          <span style={{ color: color.muted, fontSize: 13 }}>Existing tickets and tasks keep their own model.</span>
        </div>
        {note && (
          <p role="status" style={{ margin: 0, fontSize: 13, color: note.ok ? color.muted : color.errorInk }}>
            {note.text}
          </p>
        )}
      </Card>
    </section>
  )
}

function PromptEditor({ user }: { user: User }) {
  // `base` is the server's prompt the draft started from; a newer server value replaces an
  // unchanged draft but never one Pablo is editing.
  const [base, setBase] = useState(user.prompt)
  const [draft, setDraft] = useState(user.prompt)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    if (user.prompt !== base) {
      if (draft === base) setDraft(user.prompt)
      setBase(user.prompt)
    }
  }, [user.prompt, base, draft])

  const dirty = draft !== user.prompt
  const save = async () => {
    setBusy(true)
    setNote(null)
    try {
      const saved = await api.updateUser(user.id, draft)
      applyUser(saved)
      setBase(saved.prompt)
      setDraft(saved.prompt)
      setNote({ ok: true, text: 'Saved. Tasks started from now on use this prompt.' })
    } catch (err) {
      setNote({ ok: false, text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  const id = `prompt-${user.id}`
  return (
    <Card>
      <label htmlFor={id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
        <Avatar user={user} size={26} ring="none" />
        {user.name}
        <span style={{ color: color.muted, fontWeight: 400, fontFamily: font.mono, fontSize: 12 }}>@{user.handle}</span>
      </label>
      <textarea
        id={id}
        rows={8}
        value={draft}
        disabled={busy}
        onChange={(e) => {
          setDraft(e.target.value)
          setNote(null)
        }}
        style={{ ...textarea, fontSize: 13, lineHeight: '19px' }}
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
        <Button kind="primary" onClick={() => void save()} disabled={busy || !dirty || !draft.trim()}>
          {busy ? 'Saving…' : 'Save'}
        </Button>
        {dirty && !busy && (
          <Button kind="ghost" onClick={() => setDraft(user.prompt)}>
            Discard changes
          </Button>
        )}
        {note && (
          <span role="status" style={{ fontSize: 13, color: note.ok ? color.muted : color.errorInk }}>
            {note.text}
          </span>
        )}
      </div>
    </Card>
  )
}

function formatExpiry(value: string | null): string {
  if (!value) return 'no expiry reported'
  const t = Date.parse(value)
  return Number.isNaN(t) ? value : new Date(t).toLocaleString()
}

function LoginStatus({ fallback }: { fallback: Login }) {
  const [login, setLogin] = useState<Login>(fallback)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const check = async () => {
    setBusy(true)
    setError(null)
    try {
      setLogin(await api.login())
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void check()
  }, [])

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h2 style={sectionHeading}>Claude login</h2>
      <Card>
        {login.logged_in ? (
          <>
            <p style={{ margin: 0, fontWeight: 600, color: '#0F6B3A' }}>Logged in</p>
            <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '4px 16px', margin: 0, fontSize: 13 }}>
              <dt style={{ color: color.muted }}>Method</dt>
              <dd style={{ margin: 0 }}>{login.method || 'unknown'}</dd>
              <dt style={{ color: color.muted }}>Subscription</dt>
              <dd style={{ margin: 0 }}>{login.subscription || 'none reported'}</dd>
              <dt style={{ color: color.muted }}>Expires</dt>
              <dd style={{ margin: 0 }}>{formatExpiry(login.expires_at)}</dd>
            </dl>
          </>
        ) : (
          <p style={{ margin: 0, fontWeight: 600, color: color.errorInk }}>
            Not logged in — run <code style={{ fontFamily: font.mono }}>claude auth login</code> in a terminal
          </p>
        )}
        {login.detail && (
          <p style={{ margin: 0, color: color.muted, fontSize: 13, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{login.detail}</p>
        )}
        {error && (
          <p role="alert" style={{ margin: 0, color: color.errorInk, fontSize: 13 }}>
            {error}
          </p>
        )}
        <div>
          <Button kind="outline" compact onClick={() => void check()} disabled={busy}>
            {busy ? 'Checking…' : 'Check again'}
          </Button>
        </div>
      </Card>
    </section>
  )
}
