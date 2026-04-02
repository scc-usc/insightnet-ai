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

  const lastAssistantIdx = messages.reduce(
    (acc, m, i) => (m.role === "assistant" ? i : acc),
    -1
  )

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 scrollbar-thin">
      {messages.map((msg, i) => (
        <ChatMessage
          key={msg.id}
          message={msg}
          isLastAssistant={i === lastAssistantIdx}
          isStreaming={isStreaming}
          onFollowupClick={onFollowupClick}
        />
      ))}

      {/* Pipeline status indicator */}
      {isStreaming && pipelineStatus && lastAssistantIdx >= 0 && messages[lastAssistantIdx]?.content === "" && (
        <div className="flex justify-start">
          <div className="flex items-center gap-2 px-4 py-2 text-xs text-[#314158]/70">
            <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
              <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
            {pipelineStatus}
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
