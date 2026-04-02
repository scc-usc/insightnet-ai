import { Message } from "./types"

const API_BASE = "/api"

type StreamCallbacks = {
  onChunk: (text: string) => void
  onStatus: (status: string) => void
  onFollowups: (suggestions: string[]) => void
}

export async function queryStream(
  query: string,
  history: Message[],
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      history: history.map(m => ({ role: m.role, content: m.content })),
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

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Extract and emit status markers
    const statusRegex = /\{\{STATUS:(.+?)\}\}/g
    let match
    while ((match = statusRegex.exec(buffer)) !== null) {
      callbacks.onStatus(match[1])
      buffer = buffer.replace(match[0], "")
    }

    // Extract followups (appears at the end)
    const followupMatch = buffer.match(/\{\{FOLLOWUPS:(.+?)\}\}/)
    if (followupMatch) {
      const suggestions = followupMatch[1].split("||").map(s => s.trim())
      callbacks.onFollowups(suggestions)
      buffer = buffer.replace(followupMatch[0], "")
    }

    // Emit remaining text
    if (buffer) {
      callbacks.onChunk(buffer)
      buffer = ""
    }
  }
}

export async function ingestRepo(repoUrl: string): Promise<{ status: string; repo?: string }> {
  const res = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl }),
  })
  if (!res.ok) throw new Error(`Ingest failed: ${res.status}`)
  return res.json()
}

export async function ingestAll(): Promise<{ status: string; results: unknown[] }> {
  const res = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_all: true }),
  })
  if (!res.ok) throw new Error(`Ingest failed: ${res.status}`)
  return res.json()
}

export async function healthCheck(): Promise<{ supabase: string; chromadb: string; openai: string }> {
  const res = await fetch(`${API_BASE}/health`)
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
  return res.json()
}
