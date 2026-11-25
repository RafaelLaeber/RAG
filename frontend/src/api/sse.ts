import type { ChatEvent } from './types'

const KNOWN = new Set(['conversation', 'token', 'reset', 'tool', 'answer', 'error', 'done'])

/** Converte um bloco SSE (linhas "event:" e "data:") em evento tipado; ignora o que não entende. */
function parseBlock(block: string): ChatEvent | null {
  let type = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) type = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (!KNOWN.has(type)) return null
  try {
    const parsed: unknown = data.length ? JSON.parse(data.join('\n')) : {}
    return { type, data: parsed } as ChatEvent
  } catch {
    return null
  }
}

/** Lê um corpo SSE. Um evento pode chegar partido entre chunks: só vale ao ver a linha em branco. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
      let sep = buffer.indexOf('\n\n')
      while (sep !== -1) {
        const event = parseBlock(buffer.slice(0, sep))
        buffer = buffer.slice(sep + 2)
        if (event) yield event
        sep = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    const rest = parseBlock(buffer.trim())
    if (rest) yield rest
  } finally {
    reader.releaseLock()
  }
}
