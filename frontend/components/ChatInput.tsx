"use client"

import { useState, useRef, useEffect } from "react"

type ChatInputProps = {
  onSend: (text: string) => void
  disabled?: boolean
  isStreaming?: boolean
  onStop?: () => void
  draft?: string
  onDraftUsed?: () => void
}

export default function ChatInput({ onSend, disabled, isStreaming, onStop, draft, onDraftUsed }: ChatInputProps) {
  const [text, setText] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (draft) {
      setText(draft)
      onDraftUsed?.()
      setTimeout(() => {
        const el = textareaRef.current
        if (el) { el.focus(); el.setSelectionRange(draft.length, draft.length) }
      }, 0)
    }
  }, [draft, onDraftUsed])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "0"
    el.style.height = Math.min(el.scrollHeight, 140) + "px"
  }, [text])

  useEffect(() => {
    if (!isStreaming) textareaRef.current?.focus()
  }, [isStreaming])

  const handleSend = () => {
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText("")
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <div className="px-4 py-3">
      <div className="flex items-end gap-3 bg-white/80 backdrop-blur-sm rounded-2xl shadow-md px-4 py-3 border border-[#B1CBF5]/20">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          className="flex-1 text-sm outline-none text-[#1b183c] bg-transparent resize-none py-1 placeholder:text-[#314158]/35 leading-relaxed"
          placeholder={isStreaming ? "Waiting for response..." : "Describe what you need..."}
          disabled={disabled}
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop generating"
            className="shrink-0 w-9 h-9 flex items-center justify-center bg-red-500 text-white rounded-xl hover:bg-red-600 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><rect width="12" height="12" rx="2" /></svg>
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={disabled || !text.trim()}
            aria-label="Send message"
            title="Send message"
            className="shrink-0 w-9 h-9 flex items-center justify-center bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition disabled:opacity-25 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
