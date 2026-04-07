"use client"

import { useState, useRef, useCallback, useEffect } from "react"
import MessageList from "./MessageList"
import ChatInput from "./ChatInput"
import { Message } from "@/lib/types"
import { queryStream } from "@/lib/api"
import Image from "next/image"

const STORAGE_KEY = "insightnet-chat"

const CAPABILITIES = [
  {
    title: "Find tools",
    desc: "Discover modeling tools for any disease or method",
    hint: "Find tools for ",
    icon: (
      <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  {
    title: "Compare",
    desc: "See how different frameworks stack up side by side",
    hint: "Compare ",
    icon: (
      <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="18" rx="1" /><rect x="14" y="3" width="7" height="18" rx="1" />
      </svg>
    ),
  },
  {
    title: "Explain",
    desc: "Understand what a tool does and how to get started",
    hint: "How does ",
    icon: (
      <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    ),
  },
]

function loadMessages(): Message[] {
  if (typeof window === "undefined") return []
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? JSON.parse(saved) : []
  } catch {
    return []
  }
}

function saveMessages(messages: Message[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
  } catch {}
}

export default function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [pipelineStatus, setPipelineStatus] = useState<string>("")
  const abortRef = useRef<AbortController | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [draft, setDraft] = useState("")

  useEffect(() => {
    setMessages(loadMessages())
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (hydrated && messages.length > 0) saveMessages(messages)
  }, [messages, hydrated])

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
    setPipelineStatus("")
  }, [])

  const sendMessage = useCallback(async (text: string) => {
    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: text }
    const assistantId = crypto.randomUUID()
    const assistantMsg: Message = { id: assistantId, role: "assistant", content: "" }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)
    setPipelineStatus("")

    const controller = new AbortController()
    abortRef.current = controller
    const history = [...messages, userMsg]
      .filter(m => m.content.length > 0)
      .map(m => ({
        ...m,
        content: m.tools && m.tools.length > 0
          ? `${m.content}\n\n[Previously shown tools:\n${m.tools.map((t, i) => `${i + 1}. ${t.tool_name} (${t.repo_name}) — ${t.one_line}`).join("\n")}]`
          : m.content,
      }))

    try {
      await queryStream(text, history, {
        onChunk: (chunk) => {
          setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: m.content + chunk } : m))
        },
        onStatus: (status) => setPipelineStatus(status),
        onFollowups: (suggestions) => {
          setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, followups: suggestions } : m))
        },
        onTools: (tools) => {
          setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, tools } : m))
        },
      }, controller.signal)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return
      setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: m.content || "Sorry, something went wrong. Please try again." } : m))
    } finally {
      setIsStreaming(false)
      setPipelineStatus("")
      abortRef.current = null
    }
  }, [messages])

  const clearChat = useCallback(() => {
    if (isStreaming) stopStreaming()
    setMessages([])
    localStorage.removeItem(STORAGE_KEY)
  }, [isStreaming, stopStreaming])

  const isEmpty = messages.length === 0

  return (
    <div className="flex-1 flex flex-col bg-white/30 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-[#B1CBF5]/20 bg-white/40 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-2.5">
          <Image src="/logo.png" alt="Logo" width={28} height={28} />
          <h1 className="text-base font-bold text-[#1b183c]">Insight Net</h1>
        </div>
        {!isEmpty && (
          <button onClick={clearChat} className="text-xs text-[#314158]/50 hover:text-[#314158] transition px-3 py-1.5 rounded-lg hover:bg-white/50">
            New chat
          </button>
        )}
      </div>

      {/* Content area */}
      {isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6">
          <div className="text-center mb-8">
            <Image src="/logo.png" alt="Logo" width={56} height={56} className="mx-auto mb-4 opacity-80" />
            <h2 className="text-2xl font-bold text-[#1b183c]">What are you working on?</h2>
            <p className="text-sm text-[#314158]/50 mt-2 max-w-sm mx-auto">
              Describe your research and I'll help you find the right epidemic modeling tools
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 w-full max-w-xl">
            {CAPABILITIES.map((cap) => (
              <button
                key={cap.title}
                onClick={() => setDraft(cap.hint)}
                className="flex flex-col items-start gap-2 text-left bg-white/60 hover:bg-white/80 rounded-xl px-5 py-4 shadow-sm transition border border-[#B1CBF5]/20 hover:border-[#B1CBF5]/40"
              >
                <span className="text-[#314158]/60">{cap.icon}</span>
                <span className="text-sm font-semibold text-[#1b183c]">{cap.title}</span>
                <span className="text-xs text-[#314158]/50 leading-relaxed">{cap.desc}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <MessageList messages={messages} isStreaming={isStreaming} pipelineStatus={pipelineStatus} onFollowupClick={sendMessage} />
      )}

      {/* Input */}
      <div className="shrink-0 border-t border-[#B1CBF5]/15 bg-white/30 backdrop-blur-md">
        <div className="max-w-3xl mx-auto w-full">
          <ChatInput onSend={sendMessage} disabled={isStreaming} onStop={stopStreaming} isStreaming={isStreaming} draft={draft} onDraftUsed={() => setDraft("")} />
        </div>
      </div>
    </div>
  )
}
