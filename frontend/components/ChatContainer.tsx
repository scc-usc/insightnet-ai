"use client"

import { useState, useRef, useCallback } from "react"
import MessageList from "./MessageList"
import ChatInput from "./ChatInput"
import { Message } from "@/lib/types"
import { queryStream } from "@/lib/api"
import Image from "next/image"

const WELCOME_CATEGORIES = [
  { label: "Find tools", query: "Find epidemic modeling tools for COVID-19", icon: "search" },
  { label: "Compare", query: "Compare agent-based vs compartmental models", icon: "compare" },
  { label: "Explore code", query: "Show me tools with Python APIs for disease simulation", icon: "code" },
]

export default function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [pipelineStatus, setPipelineStatus] = useState<string>("")
  const abortRef = useRef<AbortController | null>(null)

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

    // Build history from existing messages (exclude the current empty assistant msg)
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
  }, [isStreaming, stopStreaming])

  const isEmpty = messages.length === 0

  return (
    <div className="w-[min(700px,95vw)] h-[min(600px,85vh)] flex flex-col rounded-2xl shadow-xl bg-white/50 backdrop-blur-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/30">
        <div className="flex items-center gap-2">
          <Image src="/logo.png" alt="Logo" width={32} height={32} />
          <h2 className="text-xl font-bold text-[#1b183c]">Insight Net</h2>
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
        <div className="flex-1 flex flex-col items-center justify-center px-6 gap-8">
          <div className="text-center">
            <Image src="/logo.png" alt="Logo" width={48} height={48} className="mx-auto mb-3 opacity-80" />
            <p className="text-lg font-semibold text-[#1b183c]">Hey! I'm InsightNet</p>
            <p className="text-sm text-[#314158]/60 mt-1">
              I help you find, compare, and explore epidemic modeling tools
            </p>
          </div>
          <div className="grid grid-cols-3 gap-3 w-full max-w-lg">
            {WELCOME_CATEGORIES.map((cat) => (
              <button
                key={cat.label}
                onClick={() => sendMessage(cat.query)}
                className="flex flex-col items-center gap-2 text-center text-xs text-[#314158] bg-white/60 hover:bg-white/80 rounded-xl px-3 py-4 shadow-sm transition border border-white/40"
              >
                <span className="text-lg">
                  {cat.icon === "search" && "\uD83D\uDD0D"}
                  {cat.icon === "compare" && "\u2696\uFE0F"}
                  {cat.icon === "code" && "\uD83D\uDCBB"}
                </span>
                <span className="font-medium">{cat.label}</span>
                <span className="text-[10px] text-[#314158]/50 leading-tight">{cat.query}</span>
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
      />
    </div>
  )
}
