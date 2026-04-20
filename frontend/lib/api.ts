import { Message, ToolCard } from "./types"
import { getIdToken } from "./firebase/auth"

const API_BASE = "/api"

/** Returns Authorization header if a Firebase token is available. */
async function authHeaders(): Promise<Record<string, string>> {
  const token = await getIdToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

type StreamCallbacks = {
  onChunk: (text: string) => void
  onStatus: (status: string) => void
  onFollowups: (suggestions: string[]) => void
  onTools: (tools: ToolCard[]) => void
}

export async function queryStream(
  query: string,
  history: Message[],
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
  model?: string
): Promise<void> {
  const auth = await authHeaders()
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({
      query,
      history: history.map(m => ({ role: m.role, content: m.content })),
      model: model || undefined,
    }),
    signal,
  })

  if (!res.ok) {
    throw new Error(`Query failed: ${res.status} ${res.statusText}`)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body")

  const decoder = new TextDecoder()
  let buffer = ""

  const processBuffer = (flush: boolean) => {
    // Walk the buffer looking for complete markers. Emit plain text up to the
    // next marker (or up to the point where a marker might be starting), then
    // consume complete markers. Any partial marker at the tail is held back
    // until the next chunk arrives, so markers split across chunks still work.
    while (true) {
      const markerStart = buffer.indexOf("{{")
      if (markerStart === -1) {
        // No marker in sight — safe to flush everything as text.
        if (buffer) {
          callbacks.onChunk(buffer)
          buffer = ""
        }
        return
      }

      // Emit any plain text that precedes the marker.
      if (markerStart > 0) {
        callbacks.onChunk(buffer.slice(0, markerStart))
        buffer = buffer.slice(markerStart)
      }

      // Now buffer starts with "{{". Look for the closing "}}".
      const markerEnd = buffer.indexOf("}}")
      if (markerEnd === -1) {
        // Incomplete marker — wait for more data (unless we're flushing at end-of-stream).
        if (flush) {
          // End of stream with an unterminated marker: emit as raw text so nothing is silently dropped.
          callbacks.onChunk(buffer)
          buffer = ""
        }
        return
      }

      const marker = buffer.slice(2, markerEnd) // strip "{{" and "}}"
      buffer = buffer.slice(markerEnd + 2)

      const colonIdx = marker.indexOf(":")
      const kind = colonIdx === -1 ? marker : marker.slice(0, colonIdx)
      const payload = colonIdx === -1 ? "" : marker.slice(colonIdx + 1)

      if (kind === "STATUS") {
        callbacks.onStatus(payload)
      } else if (kind === "TOOLS") {
        try {
          callbacks.onTools(JSON.parse(payload) as ToolCard[])
        } catch {
          /* malformed JSON — skip */
        }
      } else if (kind === "FOLLOWUPS") {
        callbacks.onFollowups(payload.split("||").map((s) => s.trim()))
      } else {
        // Unknown marker — pass through as text so it's visible rather than silently swallowed.
        callbacks.onChunk(`{{${marker}}}`)
      }
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      buffer += decoder.decode()
      processBuffer(true)
      break
    }
    buffer += decoder.decode(value, { stream: true })
    processBuffer(false)
  }
}

export async function ingestRepo(repoUrl: string): Promise<{ status: string; repo?: string }> {
  const auth = await authHeaders()
  const res = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ repo_url: repoUrl }),
  })
  if (!res.ok) throw new Error(`Ingest failed: ${res.status}`)
  return res.json()
}

export async function ingestAll(): Promise<{ status: string; results: unknown[] }> {
  const auth = await authHeaders()
  const res = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ run_all: true }),
  })
  if (!res.ok) throw new Error(`Ingest failed: ${res.status}`)
  return res.json()
}

export async function healthCheck(): Promise<{ firestore: string; openrouter: string }> {
  const res = await fetch(`${API_BASE}/health`)
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
  return res.json()
}

export type ModelInfo = {
  id: string
  name: string
  pricing: { prompt: string; completion: string }
}

export async function fetchModels(): Promise<ModelInfo[]> {
  const auth = await authHeaders()
  const res = await fetch(`${API_BASE}/models`, { headers: { ...auth } })
  if (!res.ok) throw new Error(`Models fetch failed: ${res.status}`)
  return res.json()
}
