"use client"

import { useState, useRef, useCallback, useEffect } from "react"
import MessageList from "./MessageList"
import ChatInput from "./ChatInput"
import { Message } from "@/lib/types"
import { queryStream, fetchModels, ModelInfo } from "@/lib/api"
import { ensureSignedIn } from "@/lib/firebase/auth"
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
  } catch (err) {
    console.warn("[insightnet] failed to load chat history from localStorage:", err)
    return []
  }
}

function saveMessages(messages: Message[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
  } catch (err) {
    console.warn("[insightnet] failed to save chat history to localStorage:", err)
  }
}

export default function ChatContainer() {
  const [messages, setMessages] = useState<Message[]>([])
  const messagesRef = useRef<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [pipelineStatus, setPipelineStatus] = useState<string>("")
  const abortRef = useRef<AbortController | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const [draft, setDraft] = useState("")
  const [models, setModels] = useState<ModelInfo[]>([])
  const [selectedModel, setSelectedModel] = useState<string>("")
  const selectedModelRef = useRef<string>("")
  const [showModelPicker, setShowModelPicker] = useState(false)
  const [modelSearch, setModelSearch] = useState("")
  const [modelHighlight, setModelHighlight] = useState(0)
  const modelListRef = useRef<HTMLDivElement>(null)
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set())

  // Keep refs in sync with state so callbacks can read the latest value
  // without depending on it (avoids re-creating sendMessage on every chunk).
  useEffect(() => { messagesRef.current = messages }, [messages])
  useEffect(() => { selectedModelRef.current = selectedModel }, [selectedModel])

  useEffect(() => {
    setMessages(loadMessages())
    setHydrated(true)
    // Wait for Firebase anonymous auth before fetching models
    ensureSignedIn().then(() => fetchModels()).then(m => {
      setModels(m)
      const saved = localStorage.getItem("insightnet-model")
      if (saved && m.some(model => model.id === saved)) {
        setSelectedModel(saved)
      } else if (saved) {
        console.warn(`[insightnet] saved model ${saved} no longer available, falling back to default`)
        localStorage.removeItem("insightnet-model")
      }
    }).catch((err) => {
      console.warn("[insightnet] failed to fetch models:", err)
    })
  }, [])

  useEffect(() => {
    if (hydrated && messages.length > 0) saveMessages(messages)
  }, [messages, hydrated])

  const toggleToolExpansion = useCallback((messageId: string, repoName: string) => {
    setExpandedTools(prev => {
      const key = `${messageId}:${repoName}`
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  // Close model picker when clicking outside
  useEffect(() => {
    if (!showModelPicker) return
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest("[data-model-picker]")) {
        setShowModelPicker(false)
        setModelSearch("")
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [showModelPicker])

  // Reset highlighted item when search changes or picker opens
  useEffect(() => { setModelHighlight(0) }, [modelSearch, showModelPicker])

  // Filtered list of models visible in the picker (default row is index 0).
  const filteredModels = models
    .filter(m => !modelSearch || m.id.toLowerCase().includes(modelSearch.toLowerCase()) || m.name.toLowerCase().includes(modelSearch.toLowerCase()))
    .slice(0, 50)
  // Total rows = 1 (default) + filtered count
  const totalModelRows = 1 + filteredModels.length

  const pickModelByIndex = useCallback((idx: number) => {
    if (idx === 0) {
      setSelectedModel("")
      localStorage.removeItem("insightnet-model")
    } else {
      const m = filteredModels[idx - 1]
      if (!m) return
      setSelectedModel(m.id)
      localStorage.setItem("insightnet-model", m.id)
    }
    setShowModelPicker(false)
    setModelSearch("")
  }, [filteredModels])

  const handleModelSearchKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setModelHighlight(h => Math.min(h + 1, totalModelRows - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setModelHighlight(h => Math.max(h - 1, 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      pickModelByIndex(modelHighlight)
    } else if (e.key === "Escape") {
      e.preventDefault()
      setShowModelPicker(false)
      setModelSearch("")
    }
  }, [totalModelRows, modelHighlight, pickModelByIndex])

  // Scroll highlighted row into view as the user navigates
  useEffect(() => {
    if (!showModelPicker) return
    const list = modelListRef.current
    if (!list) return
    const el = list.querySelector<HTMLElement>(`[data-model-row="${modelHighlight}"]`)
    el?.scrollIntoView({ block: "nearest" })
  }, [modelHighlight, showModelPicker])

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
    // Read latest messages via ref so this callback stays stable across renders.
    const history = [...messagesRef.current, userMsg]
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
      }, controller.signal, selectedModelRef.current || undefined)
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return
      console.warn("[insightnet] stream error:", err)
      // Append an error note instead of overwriting any partial content the user already saw.
      setMessages(prev => prev.map(m => {
        if (m.id !== assistantId) return m
        const note = "\n\n_⚠️ The response was interrupted. Please try again._"
        return { ...m, content: m.content ? m.content + note : "Sorry, something went wrong. Please try again." }
      }))
    } finally {
      setIsStreaming(false)
      setPipelineStatus("")
      abortRef.current = null
    }
  }, [])

  const clearChat = useCallback(() => {
    if (isStreaming) stopStreaming()
    setMessages([])
    localStorage.removeItem(STORAGE_KEY)
    window.scrollTo({ top: 0, behavior: "smooth" })
  }, [isStreaming, stopStreaming])

  // Before hydration completes we don't know if there's saved history,
  // so treat it as "not empty yet" to avoid flashing the welcome screen.
  const isEmpty = hydrated && messages.length === 0

  return (
    <div className="flex-1 flex flex-col bg-white/30 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-3 sm:px-6 py-3 border-b border-[#B1CBF5]/20 bg-white/40 backdrop-blur-md shrink-0 gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <Image src="/logo.png" alt="Logo" width={28} height={28} className="shrink-0" />
          <h1 className="text-base font-bold text-[#1b183c] truncate">Insight Net</h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Model selector */}
          <div className="relative" data-model-picker>
            <button
              onClick={() => setShowModelPicker(!showModelPicker)}
              aria-label="Select model"
              aria-haspopup="listbox"
              aria-expanded={showModelPicker}
              className="text-xs text-[#314158]/60 hover:text-[#314158] transition px-2 sm:px-3 py-1.5 rounded-lg hover:bg-white/50 flex items-center gap-1.5 border border-[#B1CBF5]/20"
            >
              <svg className="w-3 h-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
              <span className="max-w-[80px] sm:max-w-[150px] truncate">{selectedModel ? selectedModel.split("/").pop() : "Default"}</span>
              <svg className="w-2.5 h-2.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button>

            {showModelPicker && (
              <div
                role="listbox"
                aria-label="Available models"
                className="absolute right-0 top-full mt-1 w-[calc(100vw-1.5rem)] max-w-[20rem] sm:w-80 bg-white rounded-xl shadow-xl border border-[#B1CBF5]/30 z-50 overflow-hidden">
                <div className="p-2 border-b border-gray-100">
                  <input
                    type="text"
                    placeholder="Search models..."
                    value={modelSearch}
                    onChange={e => setModelSearch(e.target.value)}
                    onKeyDown={handleModelSearchKeyDown}
                    autoFocus
                    aria-label="Filter models"
                    aria-controls="model-list"
                    aria-activedescendant={`model-row-${modelHighlight}`}
                    className="w-full text-xs outline-none bg-gray-50 rounded-lg px-3 py-2 text-black placeholder:text-gray-400"
                  />
                </div>
                <div id="model-list" ref={modelListRef} className="max-h-64 overflow-y-auto">
                  <button
                    id="model-row-0"
                    data-model-row="0"
                    role="option"
                    aria-selected={!selectedModel}
                    onMouseEnter={() => setModelHighlight(0)}
                    onClick={() => pickModelByIndex(0)}
                    className={`w-full text-left px-3 py-2 text-xs transition flex items-center justify-between ${modelHighlight === 0 ? "bg-blue-50" : ""} ${!selectedModel ? "text-blue-700 font-medium" : "text-[#314158]"}`}
                  >
                    <span>Default (gpt-4.1-mini)</span>
                    {!selectedModel && <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>}
                  </button>
                  {filteredModels.map((m, idx) => {
                    const rowIdx = idx + 1
                    const isSelected = selectedModel === m.id
                    const isHighlighted = modelHighlight === rowIdx
                    return (
                      <button
                        key={m.id}
                        id={`model-row-${rowIdx}`}
                        data-model-row={rowIdx}
                        role="option"
                        aria-selected={isSelected}
                        onMouseEnter={() => setModelHighlight(rowIdx)}
                        onClick={() => pickModelByIndex(rowIdx)}
                        className={`w-full text-left px-3 py-2 text-xs transition flex items-center justify-between ${isHighlighted ? "bg-blue-50" : ""} ${isSelected ? "text-blue-700" : "text-[#314158]"}`}
                      >
                        <div className="min-w-0">
                          <div className="truncate font-medium">{m.name}</div>
                          <div className="text-[10px] text-gray-400 truncate">{m.id}</div>
                        </div>
                        {isSelected && <svg className="w-3 h-3 shrink-0 ml-2" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>}
                      </button>
                    )
                  })}
                  {filteredModels.length === 0 && (
                    <div className="px-3 py-4 text-xs text-gray-400 text-center">No models match &ldquo;{modelSearch}&rdquo;</div>
                  )}
                </div>
              </div>
            )}
          </div>

          {!isEmpty && (
            <button onClick={clearChat} className="text-xs text-[#314158]/50 hover:text-[#314158] transition px-3 py-1.5 rounded-lg hover:bg-white/50">
              New chat
            </button>
          )}
        </div>
      </div>

      {/* Content area */}
      {isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6">
          <div className="text-center mb-8">
            <Image src="/logo.png" alt="Logo" width={56} height={56} className="mx-auto mb-4 opacity-80" />
            <h2 className="text-2xl font-bold text-[#1b183c]">What are you working on?</h2>
            <p className="text-sm text-[#314158]/50 mt-2 max-w-sm mx-auto">
              Describe your research and I&apos;ll help you find the right epidemic modeling tools
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
        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          pipelineStatus={pipelineStatus}
          onFollowupClick={sendMessage}
          expandedTools={expandedTools}
          onToggleTool={toggleToolExpansion}
        />
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
