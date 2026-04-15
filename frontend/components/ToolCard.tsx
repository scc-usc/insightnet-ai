"use client"

import { ToolCard as ToolCardType } from "@/lib/types"

type ToolCardProps = {
  tool: ToolCardType
  onAsk?: (question: string) => void
  expanded: boolean
  onToggle: () => void
}

function cleanPreview(text: string): string {
  return text.replace(/[#*`\[\]()>_~]/g, "").replace(/\n+/g, " ").replace(/\s+/g, " ").trim()
}

export default function ToolCard({ tool, onAsk, expanded, onToggle }: ToolCardProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      onToggle()
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      aria-label={`${tool.tool_name}: ${tool.one_line}`}
      className="flex items-center gap-3 bg-white/70 rounded-lg px-3 py-2.5 border border-[#B1CBF5]/20 hover:bg-white/90 transition cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
      onClick={onToggle}
      onKeyDown={handleKeyDown}
    >
      <span className="text-[10px] font-bold text-blue-500/60 shrink-0">{tool.rank}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[#1b183c]">{tool.tool_name}</p>
        {!expanded && (
          <p className="text-[11px] text-[#314158]/60 truncate">{tool.one_line}</p>
        )}
        {expanded && (
          <div className="mt-1 space-y-1.5">
            <p className="text-xs text-[#314158]/70 leading-relaxed">{tool.one_line}</p>
            {tool.readme_preview && (
              <p className="text-[11px] text-[#314158]/50 leading-relaxed line-clamp-4">
                {cleanPreview(tool.readme_preview)}
              </p>
            )}
            <div className="flex items-center gap-3 pt-1">
              <a
                href={tool.github_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
                onKeyDown={e => e.stopPropagation()}
                className="text-[11px] font-medium text-blue-600 hover:text-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded"
              >
                GitHub &rarr;
              </a>
              {onAsk && (
                <button
                  onClick={e => { e.stopPropagation(); onAsk(`Tell me more about ${tool.tool_name}`) }}
                  onKeyDown={e => e.stopPropagation()}
                  className="text-[11px] text-[#314158]/50 hover:text-[#314158]/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 rounded"
                >
                  Tell me more
                </button>
              )}
            </div>
          </div>
        )}
      </div>
      <svg
        className={`w-3.5 h-3.5 text-[#314158]/30 shrink-0 transition ${expanded ? "rotate-180" : ""}`}
        viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"
      >
        <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
      </svg>
    </div>
  )
}
