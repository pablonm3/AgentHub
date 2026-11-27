// Colours, fonts and status looks taken from the prototype (prototype/Main.dc.html).

import type { TaskStatus } from './api'

export const color = {
  page: '#F3F4F7',
  surface: '#FFFFFF',
  column: '#E7EAEF',
  chip: '#EEF0F4',
  line: '#D9DDE5',
  lineStrong: '#8A93A6',
  ink: '#161A22',
  ink2: '#3A414E',
  muted: '#5A6272',
  accent: '#2F5BEA',
  accentInk: '#1E3FB8',
  accentSoft: '#E3EAFF',
  warnSoft: '#FFE9CC',
  warnInk: '#8A4500',
  errorSoft: '#FDE4E1',
  errorInk: '#9B1C12',
  backdrop: 'rgba(15, 18, 24, 0.55)',
} as const

// The task dialog keeps the prototype's dark terminal look.
export const dark = {
  bg: '#0F1218',
  header: '#171C26',
  footer: '#131822',
  line: '#2A3140',
  button: '#4A556B',
  text: '#D5DAE3',
  bright: '#F2F4F8',
  sub: '#A3ACBD',
  dim: '#8B94A7',
  cmd: '#8FB0FF',
  ok: '#86D9A8',
  ask: '#FFC27A',
  error: '#FF9B8F',
  userBubble: '#22305A',
  replyBubble: '#1A202B',
} as const

export const font = {
  sans: 'Inter, system-ui, sans-serif',
  display: "'Space Grotesk', sans-serif",
  mono: "'JetBrains Mono', ui-monospace, Menlo, monospace",
} as const

export interface StatusLook {
  label: string
  bg: string
  fg: string
  dot: string
}

export const statusLook: Record<TaskStatus, StatusLook> = {
  running: { label: 'Running', bg: '#E3EAFF', fg: '#1E3FB8', dot: '#2F5BEA' },
  waiting_on_user: { label: 'Waiting on user', bg: '#FFE9CC', fg: '#8A4500', dot: '#C76A00' },
  done: { label: 'Done', bg: '#E6E8EC', fg: '#3A414E', dot: '#5A6272' },
  archived: { label: 'Archived', bg: '#F1F2F5', fg: '#5A6272', dot: '#A3ACBD' },
}

/** A waiting task whose answer comes from another AI user's task, not from Pablo; the label names that AI user. */
export const waitingOnAiLook: StatusLook = { label: 'Waiting on AI user', bg: '#EEE8FB', fg: '#5A2FA6', dot: '#7C4DDB' }

export const sectionHeading = {
  margin: 0,
  fontSize: 12,
  lineHeight: '16px',
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: color.muted,
} as const

export const pageTitle = {
  margin: 0,
  fontFamily: font.display,
  fontSize: 26,
  lineHeight: '32px',
  fontWeight: 700,
  letterSpacing: '-0.02em',
} as const

export const input = {
  width: '100%',
  minHeight: 40,
  padding: '0 12px',
  border: `1px solid ${color.lineStrong}`,
  borderRadius: 9,
  background: color.surface,
  color: color.ink,
  fontSize: 14,
} as const

export const textarea = {
  width: '100%',
  padding: '10px 12px',
  border: `1px solid ${color.lineStrong}`,
  borderRadius: 10,
  background: color.surface,
  color: color.ink,
  fontSize: 14,
  lineHeight: '20px',
  resize: 'vertical',
} as const
