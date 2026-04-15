"use client"

import { useState, useCallback } from "react"
import { Message } from "@/lib/types"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import type { Components } from "react-markdown"
import ToolCard from "./ToolCard"

type ChatMessageProps = {
  message: Message
  isLastAssistant?: boolean
  isStreaming?: boolean
  onFollowupClick?: (text: string) => void
  expandedTools?: Set<string>
  onToggleTool?: (messageId: string, repoName: string) => void
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
      aria-label={copied ? "Copied to clipboard" : "Copy code"}
      className="absolute top-2 right-2 px-2 py-1 text-[10px] bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition opacity-0 group-hover:opacity-100 focus:opacity-100"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  )
}

function MessageCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [text])
  return (
    <button
      onClick={handleCopy}
      aria-label={copied ? "Copied to clipboard" : "Copy message"}
      title={copied ? "Copied!" : "Copy message"}
      className="text-[11px] text-[#314158]/40 hover:text-[#314158]/80 transition inline-flex items-center gap-1 px-1.5 py-1 rounded hover:bg-white/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
    >
      {copied ? (
        <>
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12" /></svg>
          <span>Copied</span>
        </>
      ) : (
        <>
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          <span>Copy</span>
        </>
      )}
    </button>
  )
}

function linkifySourceRefs(text: string): string {
  return text.replace(/\[source:\s*([^\]]+)\]/g, (_, repo) => `[${repo.trim()}](https://github.com/${repo.trim()})`)
}

export default function ChatMessage({ message, isLastAssistant, isStreaming, onFollowupClick, expandedTools, onToggleTool }: ChatMessageProps) {
  const isUser = message.role === "user"
  const showCursor = isLastAssistant && isStreaming && message.content.length > 0
  const showFollowups = !isStreaming && message.followups && message.followups.length > 0
  const hasTools = message.tools && message.tools.length > 0

  const displayContent = linkifySourceRefs(
    message.content.replace(/\{\{FOLLOWUPS:.+?\}\}/g, "").replace(/\{\{TOOLS:.+?\}\}/g, "").trim()
  )

  const canShowCopy = !isUser && !isStreaming && displayContent.length > 0

  const markdownComponents: Components = {
    pre: ({ children, ...props }) => {
      const codeText = extractTextFromChildren(children)
      return (<div className="relative group"><pre {...props}>{children}</pre><CopyButton text={codeText} /></div>)
    },
    a: ({ href, children, ...props }) => (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
    ),
  }

  if (isUser) {
    return (
      <div className="flex items-start gap-3">
        <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center shrink-0 mt-0.5">
          <svg className="w-3.5 h-3.5 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-[#314158]/50 mb-1">You</p>
          <p className="text-sm text-[#1b183c] whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-3">
      <div className="w-7 h-7 rounded-full bg-[#B1CBF5]/60 flex items-center justify-center shrink-0 mt-0.5">
        <svg className="w-3.5 h-3.5 text-[#314158]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
        </svg>
      </div>
      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-semibold text-[#314158]/50">InsightNet</p>
          {canShowCopy && <MessageCopyButton text={displayContent} />}
        </div>

        {displayContent ? (
          <div className="text-sm text-[#314158] prose prose-sm max-w-none prose-headings:text-[#1b183c] prose-headings:mt-3 prose-headings:mb-1 prose-p:my-1 prose-a:text-blue-600 prose-a:underline prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-pre:text-xs prose-pre:rounded-lg prose-pre:overflow-x-auto prose-table:text-xs prose-table:block prose-table:overflow-x-auto prose-li:my-0.5 prose-strong:text-[#1b183c]">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
              components={markdownComponents}
            >
              {displayContent}
            </ReactMarkdown>
            {showCursor && <span className="inline-block w-0.5 h-4 bg-[#314158]/60 ml-0.5 animate-blink align-text-bottom" />}
          </div>
        ) : !hasTools ? (
          <div className="flex items-center gap-1.5 py-1">
            <span className="w-1.5 h-1.5 bg-[#314158]/40 rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 bg-[#314158]/40 rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 bg-[#314158]/40 rounded-full animate-bounce [animation-delay:300ms]" />
          </div>
        ) : null}

        {hasTools && (
          <div className="space-y-1.5">
            {message.tools!.map(tool => {
              const expandKey = `${message.id}:${tool.repo_name}`
              return (
                <ToolCard
                  key={tool.repo_name}
                  tool={tool}
                  onAsk={onFollowupClick}
                  expanded={expandedTools?.has(expandKey) ?? false}
                  onToggle={() => onToggleTool?.(message.id, tool.repo_name)}
                />
              )
            })}
          </div>
        )}

        {showFollowups && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {message.followups!.map((suggestion) => (
              <button key={suggestion} onClick={() => onFollowupClick?.(suggestion)}
                className="text-xs text-[#314158]/70 bg-white/60 hover:bg-white/90 border border-[#B1CBF5]/30 rounded-full px-3 py-1.5 transition shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400">
                {suggestion}
              </button>
            ))}
          </div>
        )}
      </div>
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
