import { describe, expect, it } from 'vitest'
import { mentionedHandles, parts } from './mentions'

const HANDLES = ['Pablo', 'DataScientist', 'Engineer', 'DevOps']

describe('parts', () => {
  it('marks mentions of known handles and keeps the rest as text', () => {
    expect(parts('Hi @Engineer, please check', HANDLES)).toEqual([
      { text: 'Hi ', mention: null },
      { text: '@Engineer', mention: 'Engineer' },
      { text: ', please check', mention: null },
    ])
  })

  it('matches handles case-insensitively and returns the canonical spelling', () => {
    expect(parts('@devops go', HANDLES)).toEqual([
      { text: '@devops', mention: 'DevOps' },
      { text: ' go', mention: null },
    ])
  })

  it('leaves unknown handles and e-mail addresses as plain text', () => {
    const result = parts('ask @Maya or mail pablo@Engineer.dev', HANDLES)
    expect(result.every((p) => p.mention === null)).toBe(true)
    expect(result.map((p) => p.text).join('')).toBe('ask @Maya or mail pablo@Engineer.dev')
  })

  it('does not match a longer word that starts with a handle', () => {
    expect(parts('@Engineers', HANDLES)).toEqual([{ text: '@Engineers', mention: null }])
  })

  it('handles empty text and text without mentions', () => {
    expect(parts('', HANDLES)).toEqual([])
    expect(parts('no mentions here', HANDLES)).toEqual([{ text: 'no mentions here', mention: null }])
  })

  it('rebuilds the original text', () => {
    const text = '@Pablo and @DataScientist: see @DevOps.\n@Engineer'
    expect(parts(text, HANDLES).map((p) => p.text).join('')).toBe(text)
  })
})

describe('mentionedHandles', () => {
  it('lists each mentioned handle once in order of first mention', () => {
    expect(mentionedHandles('@DevOps then @engineer and @DevOps again', HANDLES)).toEqual(['DevOps', 'Engineer'])
  })

  it('returns nothing without known mentions', () => {
    expect(mentionedHandles('plain text, @Nobody', HANDLES)).toEqual([])
  })
})
