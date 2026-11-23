interface Placed {
  id: number
  stage: string
  position: number
}

/** The cards of one stage in board order: by position, then by id. */
export function cardsOf<T extends Placed>(cards: T[], stage: string): T[] {
  return cards.filter((c) => c.stage === stage).sort((a, b) => a.position - b.position || a.id - b.id)
}

/**
 * The position for `movingId` dropped into `stage`, before the card `beforeId`, or at the end
 * of the column when `beforeId` is null: halfway between its new neighbours.
 */
export function positionFor(cards: Placed[], movingId: number, stage: string, beforeId: number | null): number {
  const column = cardsOf(cards, stage).filter((c) => c.id !== movingId)
  const at = beforeId === null ? -1 : column.findIndex((c) => c.id === beforeId)
  if (at < 0) {
    const last = column[column.length - 1]
    return last ? last.position + 1 : 1
  }
  const next = column[at]
  const prev = column[at - 1]
  return prev ? (prev.position + next.position) / 2 : next.position - 1
}
