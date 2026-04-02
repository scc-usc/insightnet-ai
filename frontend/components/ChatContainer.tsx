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
    icon: "\uD83D\uDD0D",
    title: "Find tools",
    desc: "Discover modeling tools for any disease or method",
    hint: "Find tools for ",
  },
  {
    icon: "\u2696\uFE0F",
    title: "Compare",
    desc: "See how different frameworks stack up",
    hint: "Compare ",
  },
  {
    icon: "\uD83D\uDCA1",
    title: "Explain",
    desc: "Understand what a tool does and how to use it",
    hint: "How does ",
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
  } catch { /* quota exceeded — ignore */ }
}

export default function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [pipelineStatus, setPipelineStatus] = useState<string>("")
  const abortRef = useRef<AbortController | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [draft, setDraft] = useState("")

  // Load from localStorage on mount
  useEffect(() => {
    setMessages(loadMessages())
    setHydrated(true)
  }, [])

  // Save to localStorage when messages change
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
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    }

    const assistantId = crypto.randomUUID()
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)
    setPipelineStatus("")

    const controller = new AbortController()
    abortRef.current = controller

    const history = [...messages, userMsg].filter(m => m.content.length > 0)

    try {
      await queryStream(
        text,
        history,
        {
          onChunk: (chunk) => {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? { ...m, content: m.content + chunk }
                  : m
              )
            )
          },
          onStatus: (status) => {
            setPipelineStatus(status)
          },
          onFollowups: (suggestions) => {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? { ...m, followups: suggestions }
                  : m
              )
            )
          },
          onTools: (tools) => {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? { ...m, tools }
                  : m
              )
            )
          },
        },
        controller.signal
      )
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, content: m.content || "Sorry, something went wrong. Please try again." }
            : m
        )
      )
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
    <div className="w-full max-w-2xl h-full flex flex-col rounded-2xl shadow-xl bg-white/50 backdrop-blur-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/30 shrink-0">
        <div className="flex items-center gap-2">
          <Image src="/logo.png" alt="Logo" width={28} height={28} />
          <h2 className="text-lg font-bold text-[#1b183c]">Insight Net</h2>
        </div>
        {!isEmpty && (
          <button
            onClick={clearChat}
            className="text-xs text-[#314158]/60 hover:text-[#314158] transition px-2 py-1 rounded-md hover:bg-white/40"
          >
            Clear chat
          </button>
        )}
      </div>

      {/* Messages or Welcome */}
      {isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6 gap-6">
          <div className="text-center">
            <Image src="/logo.png" alt="Logo" width={44} height={44} className="mx-auto mb-2 opacity-80" />
            <p className="text-lg font-semibold text-[#1b183c]">Hey! I'm InsightNet</p>
            <p className="text-sm text-[#314158]/60 mt-1 max-w-xs mx-auto">
              Describe what you're working on and I'll help you find the right epidemic modeling tools
            </p>
          </div>
          <div className="grid grid-cols-3 gap-3 w-full max-w-md">
            {CAPABILITIES.map((cap) => (
              <button
                key={cap.title}
                onClick={() => setDraft(cap.hint)}
                className="flex flex-col items-center gap-1.5 text-center text-xs text-[#314158] bg-white/60 hover:bg-white/80 rounded-xl px-3 py-3.5 shadow-sm transition border border-white/40"
              >
                <span className="text-lg">{cap.icon}</span>
                <span className="font-medium">{cap.title}</span>
                <span className="text-[10px] text-[#314158]/50 leading-tight">{cap.desc}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          pipelineStatus={pipelineStatus}
          onFollowupClick={sendMessage}
        />
      )}

      <ChatInput
        onSend={sendMessage}
        disabled={isStreaming}
        onStop={stopStreaming}
        isStreaming={isStreaming}
        draft={draft}
        onDraftUsed={() => setDraft("")}
      />
    </div>
  )
}
