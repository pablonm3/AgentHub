// Voice input with the browser's speech recognition. The browser sends the audio to its
// vendor's recognition service (the default mode); the app never asks for on-device
// recognition and never receives audio.

/** The language every dictation is recognised in. */
export const DICTATION_LANG = 'en-US'

/** The text with a spoken phrase added at its end, after one space unless it ends in white space. */
export function appendDictation(text: string, spoken: string): string {
  const phrase = spoken.trim()
  if (!phrase) return text
  const separator = text && !/\s$/.test(text) ? ' ' : ''
  return `${text}${separator}${phrase}`
}

const BLOCKED = 'Microphone access is blocked. Allow the microphone for this site in the browser, then try again.'
const FAILED = 'Voice input failed.'

/** The message for a recognition error code; null for silence and for a session the app ended. */
export function dictationErrorMessage(code: string): string | null {
  switch (code) {
    case 'no-speech':
    case 'aborted':
      return null
    case 'not-allowed':
      return BLOCKED
    case 'network':
      return 'Voice input failed: the speech recognition service could not be reached.'
    case 'audio-capture':
      return 'Voice input failed: no microphone was found.'
    default:
      return FAILED
  }
}

// TypeScript's DOM library declares the event types but not the recogniser class, so the
// part the app uses is declared here, structurally.
export interface RecognitionResultEvent {
  readonly resultIndex: number
  readonly results: ArrayLike<ArrayLike<{ readonly transcript: string }> & { readonly isFinal: boolean }>
}

export interface RecognitionErrorEvent {
  readonly error: string
}

export interface Recognizer {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: RecognitionResultEvent) => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}

export type RecognizerCtor = new () => Recognizer

/** The browser's recogniser class, or null when the browser has none. */
export function recognizerCtor(): RecognizerCtor | null {
  const scope = globalThis as { SpeechRecognition?: RecognizerCtor; webkitSpeechRecognition?: RecognizerCtor }
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null
}

export interface DictationSession {
  /** Asks the browser to finish; the phrase being spoken still arrives before the session ends. */
  stop(): void
  /** Ends the session now: nothing arrives afterwards. */
  cancel(): void
}

export interface DictationHandlers {
  /** Each final phrase, trimmed and never empty. */
  onText(phrase: string): void
  /** Runs once per session: with a message when it failed, null otherwise. */
  onEnd(message: string | null): void
}

// At most one session listens at a time, whichever field started it.
let active: DictationSession | null = null

/** Ends the session that is listening, if any, and starts a continuous one. */
export function startDictation(Ctor: RecognizerCtor, handlers: DictationHandlers): DictationSession {
  active?.cancel()
  const recognizer = new Ctor()
  recognizer.lang = DICTATION_LANG
  recognizer.continuous = true
  recognizer.interimResults = false

  let ended = false
  let pendingError: string | null = null
  const finish = (errorMessage: string | null) => {
    if (ended) return
    ended = true
    recognizer.onresult = null
    recognizer.onerror = null
    recognizer.onend = null
    if (active === session) active = null
    handlers.onEnd(errorMessage)
  }

  recognizer.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i]
      const phrase = result.isFinal ? result[0].transcript.trim() : ''
      if (phrase) handlers.onText(phrase)
    }
  }
  // The browser fires `error`, then `end`: the message is reported when the session ends.
  recognizer.onerror = (event) => {
    pendingError = dictationErrorMessage(event.error)
  }
  recognizer.onend = () => finish(pendingError)

  const session: DictationSession = {
    stop: () => {
      if (!ended) recognizer.stop()
    },
    cancel: () => {
      if (ended) return
      // The handlers go first, so the `aborted` error and the `end` of the abort reach nobody.
      finish(null)
      try {
        recognizer.abort()
      } catch {
        // Already stopped.
      }
    },
  }
  active = session
  try {
    recognizer.start()
  } catch {
    finish(FAILED)
  }
  return session
}
