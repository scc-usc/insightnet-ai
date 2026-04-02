"use client"

import ChatMessage from "./ChatMessage"
import { Message } from "@/lib/types"
import { useEffect, useRef } from "react"

type MessageListProps = {
  messages: Message[]
  isStreaming?: boolean
  pipelineStatus?: string
  onFollowupClick?: (text: string) => void
}

export default function MessageList({ messages, isStreaming, pipelineStatus, onFollowupClick }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, pipelineStatus])

  const lastAssistantIdx = messages.reduce((acc, m, i) => (m.role === "assistant" ? i : acc), -1)

  // Group messages into exchanges (user + assistant pairs)
  const exchanges: { user: Message; assistant?: Message }[] = []
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].role === "user") {
      exchanges.push({ user: messages[i], assistant: messages[i + 1]?.role === "assistant" ? messages[i + 1] : undefined })
      if (messages[i + 1]?.role === "assistant") i++
    }
  }

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-3xl mx-auto w-full px-6 py-4">
        {exchanges.map((exchange, exIdx) => (
          <div key={exchange.user.id}>
            {exIdx > 0 && <div className="border-t border-[#B1CBF5]/10 my-6" />}
            <div className="space-y-3">
              <ChatMessage message={exchange.user} />
              {exchange.assistant && (
                <ChatMessage
                  message={exchange.assistant}
                  isLastAssistant={messages.indexOf(exchange.assistant) === lastAssistantIdx}
                  isStreaming={isStreaming}
                  onFollowupClick={onFollowupClick}
                />
              )}
            </div>
          </div>
        ))}

        {isStreaming && pipelineStatus && lastAssistantIdx >= 0 && messages[lastAssistantIdx]?.content === "" && !messages[lastAssistantIdx]?.tools?.length && (
          <div className="flex items-center gap-2 py-3 text-xs text-[#314158]/60">
            <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
              <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
            {pipelineStatus}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
