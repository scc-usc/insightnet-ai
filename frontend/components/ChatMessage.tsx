"use client"

import { useState, useCallback } from "react"
import { Message } from "@/lib/types"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { Components } from "react-markdown"
import ToolCard from "./ToolCard"

type ChatMessageProps = {
  message: Message
  isLastAssistant?: boolean
  isStreaming?: boolean
  onFollowupClick?: (text: string) => void
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [text])

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 px-2 py-1 text-[10px] bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition opacity-0 group-hover:opacity-100"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  )
}

function linkifySourceRefs(text: string): string {
  return text.replace(
    /\[source:\s*([^\]]+)\]/g,
    (_, repo) => `[${repo.trim()}](https://github.com/${repo.trim()})`
  )
}

export default function ChatMessage({ message, isLastAssistant, isStreaming, onFollowupClick }: ChatMessageProps) {
  const isUser = message.role === "user"
  const showCursor = isLastAssistant && isStreaming && message.content.length > 0
  const showFollowups = !isStreaming && message.followups && message.followups.length > 0
  const hasTools = message.tools && message.tools.length > 0

  const displayContent = linkifySourceRefs(
    message.content.replace(/\{\{FOLLOWUPS:.+?\}\}/g, "").replace(/\{\{TOOLS:.+?\}\}/g, "").trim()
  )

  const markdownComponents: Components = {
    pre: ({ children, ...props }) => {
      const codeText = extractTextFromChildren(children)
      return (
        <div className="relative group">
          <pre {...props}>{children}</pre>
          <CopyButton text={codeText} />
        </div>
      )
    },
    a: ({ href, children, ...props }) => (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    ),
  }

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="px-4 py-2 rounded-xl rounded-tr-none max-w-[75%] text-sm shadow-sm bg-white text-[#314158]">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-start gap-2">
      {/* Tool cards (appear before text) */}
      {hasTools && (
        <div className="w-full space-y-2">
          {message.tools!.map(tool => (
            <ToolCard key={tool.repo_name} tool={tool} onAsk={onFollowupClick} />
          ))}
        </div>
      )}

      {/* Conversational text */}
      {displayContent ? (
        <div className="w-full text-sm text-[#314158] px-1">
          <div className="prose prose-sm max-w-none prose-headings:text-[#1b183c] prose-headings:mt-3 prose-headings:mb-1 prose-p:my-1 prose-a:text-blue-600 prose-a:underline prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:text-xs prose-pre:rounded-lg prose-table:text-xs prose-li:my-0.5 prose-strong:text-[#1b183c]">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {displayContent}
            </ReactMarkdown>
            {showCursor && <span className="inline-block w-0.5 h-4 bg-[#314158]/60 ml-0.5 animate-blink align-text-bottom" />}
          </div>
        </div>
      ) : !hasTools ? (
        <div className="flex items-center gap-1.5 py-1 px-1">
          <span className="w-1.5 h-1.5 bg-[#314158]/40 rounded-full animate-bounce [animation-delay:0ms]" />
          <span className="w-1.5 h-1.5 bg-[#314158]/40 rounded-full animate-bounce [animation-delay:150ms]" />
          <span className="w-1.5 h-1.5 bg-[#314158]/40 rounded-full animate-bounce [animation-delay:300ms]" />
        </div>
      ) : null}

      {/* Follow-up suggestions */}
      {showFollowups && (
        <div className="flex flex-wrap gap-1.5 mt-1">
          {message.followups!.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => onFollowupClick?.(suggestion)}
              className="text-xs text-[#314158]/80 bg-white/70 hover:bg-white/90 border border-[#B1CBF5]/40 rounded-full px-3 py-1.5 transition shadow-sm"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function extractTextFromChildren(children: React.ReactNode): string {
  if (typeof children === "string") return children
  if (Array.isArray(children)) return children.map(extractTextFromChildren).join("")
  if (children && typeof children === "object") {
    const obj = children as unknown as Record<string, unknown>
    if ("props" in obj && obj.props && typeof obj.props === "object") {
      const props = obj.props as { children?: React.ReactNode }
      return extractTextFromChildren(props.children)
    }
  }
  return ""
}
