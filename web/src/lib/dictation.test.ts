import { afterEach, describe, expect, it } from 'vitest'
import {
  appendDictation,
  dictationErrorMessage,
  startDictation,
  type DictationSession,
  type RecognitionErrorEvent,
  type RecognitionResultEvent,
  type Recognizer,
} from './dictation'

/** A recogniser that records what the app sets and calls, and lets a test fire its events. */
class FakeRecognizer implements Recognizer {
  static made: FakeRecognizer[] = []
  static log: string[] = []
  lang = ''
  continuous = false
  interimResults = false
  onresult: ((event: RecognitionResultEvent) => void) | null = null
  onerror: ((event: RecognitionErrorEvent) => void) | null = null
  onend: (() => void) | null = null
  calls: string[] = []
  processLocallyWritten = false

  constructor() {
    FakeRecognizer.made.push(this)
  }

  get processLocally() {
    return false
  }

  set processLocally(_value: boolean) {
    this.processLocallyWritten = true
  }

  start() {
    this.calls.push('start')
    FakeRecognizer.log.push(`start ${FakeRecognizer.made.indexOf(this)}`)
  }

  stop() {
    this.calls.push('stop')
  }

  abort() {
    this.calls.push('abort')
  }

  say(transcript: string, isFinal = true) {
    this.onresult?.({ resultIndex: 0, results: [Object.assign([{ transcript }], { isFinal })] })
  }

  fail(code: string) {
    this.onerror?.({ error: code })
    this.onend?.()
  }
}

class RefusingRecognizer extends FakeRecognizer {
  start(): void {
    throw new Error('InvalidStateError')
  }
}

const sessions: DictationSession[] = []

function start(Ctor: new () => Recognizer = FakeRecognizer) {
  const texts: string[] = []
  const ends: Array<string | null> = []
  const session = startDictation(Ctor, { onText: (t) => texts.push(t), onEnd: (m) => ends.push(m) })
  sessions.push(session)
  return { session, texts, ends, fake: FakeRecognizer.made[FakeRecognizer.made.length - 1] }
}

afterEach(() => {
  for (const s of sessions.splice(0)) s.cancel()
  FakeRecognizer.made = []
  FakeRecognizer.log = []
})

describe('appendDictation', () => {
  it('puts the phrase alone into an empty field', () => {
    expect(appendDictation('', 'hello there')).toBe('hello there')
  })

  it('adds exactly one space after text ending in a letter', () => {
    expect(appendDictation('Fix the bug', 'in the sender')).toBe('Fix the bug in the sender')
  })

  it('adds no space after a space or a line break', () => {
    expect(appendDictation('Fix ', 'it')).toBe('Fix it')
    expect(appendDictation('Fix\n', 'it')).toBe('Fix\nit')
  })

  it('trims the phrase', () => {
    expect(appendDictation('Fix', '  it now ')).toBe('Fix it now')
  })

  it('leaves the text unchanged for an empty phrase', () => {
    expect(appendDictation('Fix', '   ')).toBe('Fix')
  })
})

describe('dictationErrorMessage', () => {
  it('says the microphone is blocked when access is refused', () => {
    expect(dictationErrorMessage('not-allowed')).toMatch(/^Microphone access is blocked/)
  })

  it('says voice input failed for any other failure', () => {
    expect(dictationErrorMessage('network')).toMatch(/^Voice input failed: .*could not be reached/)
    expect(dictationErrorMessage('audio-capture')).toMatch(/^Voice input failed: no microphone/)
    expect(dictationErrorMessage('service-not-allowed')).toBe('Voice input failed.')
  })

  it('has no message for silence or for a session the app ended', () => {
    expect(dictationErrorMessage('no-speech')).toBeNull()
    expect(dictationErrorMessage('aborted')).toBeNull()
  })
})

describe('startDictation', () => {
  it('starts a continuous English session and leaves on-device processing alone', () => {
    const { fake } = start()
    expect(fake.lang).toBe('en-US')
    expect(fake.continuous).toBe(true)
    expect(fake.interimResults).toBe(false)
    expect(fake.processLocallyWritten).toBe(false)
    expect(fake.calls).toEqual(['start'])
  })

  it('passes on final phrases, trimmed, one after the other, and skips provisional ones', () => {
    const { fake, texts } = start()
    fake.say(' first sentence')
    fake.say('provi', false)
    fake.say(' second sentence ')
    expect(texts).toEqual(['first sentence', 'second sentence'])
  })

  it('reads only the results from resultIndex on', () => {
    const { fake, texts } = start()
    const result = (transcript: string) => Object.assign([{ transcript }], { isFinal: true })
    fake.onresult?.({ resultIndex: 1, results: [result('old'), result('new')] })
    expect(texts).toEqual(['new'])
  })

  it('still delivers the last phrase after stop, then ends once', () => {
    const { session, fake, texts, ends } = start()
    session.stop()
    expect(fake.calls).toEqual(['start', 'stop'])
    fake.say('last words')
    fake.onend?.()
    expect(texts).toEqual(['last words'])
    expect(ends).toEqual([null])
  })

  it('ends without a message when the browser ends the session by itself', () => {
    const { fake, ends } = start()
    fake.onend?.()
    expect(ends).toEqual([null])
  })

  it('cancel aborts, ends once, and lets nothing through afterwards', () => {
    const { session, fake, texts, ends } = start()
    session.cancel()
    expect(fake.calls).toEqual(['start', 'abort'])
    expect(ends).toEqual([null])
    fake.say('too late')
    fake.fail('aborted')
    session.cancel()
    session.stop()
    expect(texts).toEqual([])
    expect(ends).toEqual([null])
    expect(fake.calls).toEqual(['start', 'abort'])
  })

  it('ends the listening session before a second one starts', () => {
    const first = startDictation(FakeRecognizer, {
      onText: () => {},
      onEnd: () => FakeRecognizer.log.push('first ended'),
    })
    sessions.push(first)
    const firstFake = FakeRecognizer.made[0]
    const second = start()
    expect(FakeRecognizer.log).toEqual(['start 0', 'first ended', 'start 1'])
    expect(firstFake.calls).toEqual(['start', 'abort'])
    firstFake.say('to the wrong field')
    second.fake.say('to the right field')
    expect(second.texts).toEqual(['to the right field'])
  })

  it('reports a refused microphone when the session ends', () => {
    const { fake, ends } = start()
    fake.fail('not-allowed')
    expect(ends).toEqual([dictationErrorMessage('not-allowed')])
  })

  it('reports a failure for a network error and none for silence', () => {
    const failed = start()
    failed.fake.fail('network')
    expect(failed.ends).toEqual([dictationErrorMessage('network')])
    const silent = start()
    silent.fake.fail('no-speech')
    expect(silent.ends).toEqual([null])
  })

  it('ends with a failure when the browser refuses to start', () => {
    const { ends } = start(RefusingRecognizer)
    expect(ends).toEqual(['Voice input failed.'])
  })
})
