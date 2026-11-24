import { useEffect, useRef, useState } from 'react'
import { appendDictation, recognizerCtor, startDictation, type DictationSession } from './lib/dictation'
import { color, dark } from './theme'

/** What one field knows about its voice input. */
export interface Dictation {
  supported: boolean
  listening: boolean
  /** The message of the last session that failed; cleared by the next start. */
  error: string | null
  toggle(): void
  /** Ends the session now; safe to call when nothing is listening. */
  cancel(): void
}

/** Voice input for one field; `setText` is the field's state setter, and phrases are appended to its text. */
export function useDictation(setText: (update: (text: string) => string) => void): Dictation {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const session = useRef<DictationSession | null>(null)
  const Ctor = recognizerCtor()

  const cancel = () => session.current?.cancel()
  const toggle = () => {
    if (listening) {
      // Idle at once; the phrase being finished still lands when the browser delivers it.
      session.current?.stop()
      setListening(false)
      return
    }
    if (!Ctor) return
    cancel()
    setError(null)
    setListening(true)
    // onEnd may run before startDictation returns (a start that fails at once).
    session.current = startDictation(Ctor, {
      onText: (phrase) => setText((text) => appendDictation(text, phrase)),
      onEnd: (message) => {
        setListening(false)
        setError(message)
      },
    })
  }
  return { supported: Ctor !== null, listening, error, toggle, cancel }
}

/** The microphone control beside a field; nothing when the browser has no speech recognition. */
export function MicButton({ voice, disabled = false, darkMode = false }: { voice: Dictation; disabled?: boolean; darkMode?: boolean }) {
  // The session ends when the control leaves the screen: a closed form or dialog, another page.
  // `cancel` reads the session from a ref, so the one captured at mount ends the current session.
  useEffect(() => () => voice.cancel(), [])
  if (!voice.supported) return null

  const on = voice.listening
  const label = on ? 'Stop voice input' : 'Start voice input'
  const idleInk = darkMode ? '#E6E9EF' : color.ink2
  const onBackground = darkMode ? dark.cmd : color.accent
  const onInk = darkMode ? dark.bg : '#FFFFFF'
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={on}
      className={on ? undefined : darkMode ? 'wb-ghost-dark' : 'wb-ghost'}
      disabled={disabled}
      onClick={voice.toggle}
      style={{
        flex: '0 0 auto',
        width: 44,
        height: 44,
        display: 'grid',
        placeItems: 'center',
        border: 0,
        borderRadius: 9,
        background: on ? onBackground : 'transparent',
        color: on ? onInk : idleInk,
      }}
    >
      <MicIcon pulse={on} />
    </button>
  )
}

function MicIcon({ pulse }: { pulse: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ animation: pulse ? 'wb-pulse 1.4s ease-in-out infinite' : 'none' }}
    >
      <rect x="5.5" y="1.5" width="5" height="8" rx="2.5" />
      <path d="M3 7.5a5 5 0 0 0 10 0" />
      <path d="M8 12.5v2" />
    </svg>
  )
}
