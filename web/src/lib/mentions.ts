// @mentions of known handles (Pablo, DataScientist, Engineer, DevOps), matched case-insensitively.
// An "@" right after a letter, digit or underscore (an e-mail address) is not a mention.

export interface TextPart {
  text: string
  /** The handle as the user list spells it when this part is a mention, else null. */
  mention: string | null
}

const MENTION = /(?<![A-Za-z0-9_])(@[A-Za-z]+)/

function handleIndex(handles: Iterable<string>): Map<string, string> {
  const index = new Map<string, string>()
  for (const h of handles) index.set(h.toLowerCase(), h)
  return index
}

/** Split text into plain parts and mention parts; joined back, the parts give the text. */
export function parts(text: string, handles: Iterable<string>): TextPart[] {
  const index = handleIndex(handles)
  return String(text)
    .split(MENTION)
    .filter((piece) => piece !== '')
    .map((piece) => {
      const known = piece.charAt(0) === '@' ? index.get(piece.slice(1).toLowerCase()) : undefined
      return { text: piece, mention: known ?? null }
    })
}

/** The known handles the text mentions, each once, in order of first mention. */
export function mentionedHandles(text: string, handles: Iterable<string>): string[] {
  const seen: string[] = []
  for (const part of parts(text, handles)) {
    if (part.mention && !seen.includes(part.mention)) seen.push(part.mention)
  }
  return seen
}
