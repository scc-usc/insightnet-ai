"use client"

import ChatMessage from "./ChatMessage"
import ErrorBoundary from "./ErrorBoundary"
import { Message } from "@/lib/types"
import { useEffect, useRef, useState } from "react"

type MessageListProps = {
  messages: Message[]
  isStreaming?: boolean
  pipelineStatus?: string
  onFollowupClick?: (text: string) => void
  expandedTools?: Set<string>
  onToggleTool?: (messageId: string, repoName: string) => void
}

// Scroll is considered "near bottom" if the user is within this many pixels
// of the end of the conversation — used to decide whether to auto-follow the stream.
const NEAR_BOTTOM_THRESHOLD_PX = 120

export default function MessageList({ messages, isStreaming, pipelineStatus, onFollowupClick, expandedTools, onToggleTool }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [stickToBottom, setStickToBottom] = useState(true)
  const prevLenRef = useRef(messages.length)
  const prevStreamingRef = useRef(isStreaming)

  // Track whether the user is currently near the bottom of the scroll container.
  // If they scroll up to re-read, we pause auto-scroll so we don't yank them back.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      setStickToBottom(distanceFromBottom < NEAR_BOTTOM_THRESHOLD_PX)
    }
    el.addEventListener("scroll", handleScroll, { passive: true })
    return () => el.removeEventListener("scroll", handleScroll)
  }, [])

  useEffect(() => {
    if (messages.length === 0) {
      containerRef.current?.scrollTo({ top: 0 })
      prevLenRef.current = 0
      return
    }

    const newMessage = messages.length > prevLenRef.current
    const justFinishedStreaming = prevStreamingRef.current && !isStreaming
    prevLenRef.current = messages.length
    prevStreamingRef.current = !!isStreaming

    if (!stickToBottom) return
    // During streaming: jump instantly so there's no animation-per-token jank.
    // Smooth-scroll only for the one-shot events: a new message arriving, or streaming ending.
    const behavior: ScrollBehavior = (isStreaming && !newMessage) ? "auto" : "smooth"
    bottomRef.current?.scrollIntoView({ behavior })
    void justFinishedStreaming // read so the ref update above isn't flagged unused
  }, [messages, pipelineStatus, isStreaming, stickToBottom])

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
    <div ref={containerRef} className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-3xl mx-auto w-full px-4 sm:px-6 py-4">
        {exchanges.map((exchange, exIdx) => (
          <div key={exchange.user.id}>
            {exIdx > 0 && <div className="border-t border-[#B1CBF5]/10 my-6" />}
            <div className="space-y-3">
              <ErrorBoundary fallback={<div className="text-xs text-red-500 py-2">Failed to render this message.</div>}>
                <ChatMessage message={exchange.user} />
                {exchange.assistant && (
                  <ChatMessage
                    message={exchange.assistant}
                    isLastAssistant={messages.indexOf(exchange.assistant) === lastAssistantIdx}
                    isStreaming={isStreaming}
                    onFollowupClick={onFollowupClick}
                    expandedTools={expandedTools}
                    onToggleTool={onToggleTool}
                  />
                )}
              </ErrorBoundary>
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
