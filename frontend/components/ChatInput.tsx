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

  // Accept draft from parent (e.g., when user clicks a capability card)
  useEffect(() => {
    if (draft) {
      setText(draft)
      onDraftUsed?.()
      // Focus and place cursor at end
      setTimeout(() => {
        const el = textareaRef.current
        if (el) {
          el.focus()
          el.setSelectionRange(draft.length, draft.length)
        }
      }, 0)
    }
  }, [draft, onDraftUsed])

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "0"
    el.style.height = Math.min(el.scrollHeight, 120) + "px"
  }, [text])

  // Re-focus after streaming ends
  useEffect(() => {
    if (!isStreaming) textareaRef.current?.focus()
  }, [isStreaming])

  const handleSend = () => {
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText("")
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="px-4 pb-4 pt-2 shrink-0">
      <div className="flex items-end gap-2 bg-white rounded-xl shadow-sm px-3 py-2 border border-white/40">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          className="flex-1 text-sm outline-none text-black bg-transparent resize-none py-1.5 placeholder:text-[#314158]/40"
          placeholder={isStreaming ? "Waiting for response..." : "Describe what you need..."}
          disabled={disabled}
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            className="shrink-0 w-8 h-8 flex items-center justify-center bg-red-500 text-white rounded-lg hover:bg-red-600 transition"
            title="Stop"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
              <rect width="12" height="12" rx="1" />
            </svg>
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={disabled || !text.trim()}
            className="shrink-0 w-8 h-8 flex items-center justify-center bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-30"
            title="Send"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
