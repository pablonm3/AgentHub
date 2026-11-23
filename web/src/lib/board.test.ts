import { describe, expect, it } from 'vitest'
import { cardsOf, positionFor } from './board'

const cards = [
  { id: 1, stage: 'todo', position: 2 },
  { id: 2, stage: 'todo', position: 1 },
  { id: 3, stage: 'todo', position: 3 },
  { id: 4, stage: 'done', position: 1 },
]

describe('cardsOf', () => {
  it('orders a stage by position', () => {
    expect(cardsOf(cards, 'todo').map((c) => c.id)).toEqual([2, 1, 3])
    expect(cardsOf(cards, 'backlog')).toEqual([])
  })
})

describe('positionFor', () => {
  it('puts a card at the end of a column, or first in an empty one', () => {
    expect(positionFor(cards, 4, 'todo', null)).toBe(4)
    expect(positionFor(cards, 2, 'backlog', null)).toBe(1)
  })

  it('puts a card between its new neighbours', () => {
    expect(positionFor(cards, 4, 'todo', 1)).toBe(1.5)
    expect(positionFor(cards, 4, 'todo', 2)).toBe(0)
  })

  it('ignores the moving card itself when it stays in its column', () => {
    expect(positionFor(cards, 2, 'todo', 3)).toBe(2.5)
    expect(positionFor(cards, 3, 'todo', null)).toBe(3)
  })
})
