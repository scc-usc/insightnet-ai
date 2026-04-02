"use client"

import { useState } from "react"
import { ToolCard as ToolCardType } from "@/lib/types"

type ToolCardProps = {
  tool: ToolCardType
  onAsk?: (question: string) => void
}

export default function ToolCard({ tool, onAsk }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false)

  const difficultyColor = {
    low: "bg-green-100 text-green-700",
    medium: "bg-yellow-100 text-yellow-700",
    high: "bg-red-100 text-red-700",
  }[tool.difficulty] || "bg-gray-100 text-gray-600"

  return (
    <div className="bg-white/80 rounded-lg border border-[#B1CBF5]/30 shadow-sm overflow-hidden transition hover:shadow-md">
      {/* Main card content */}
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-blue-600/70">#{tool.rank}</span>
              <h3 className="text-sm font-semibold text-[#1b183c] truncate">{tool.tool_name}</h3>
            </div>
            <p className="text-xs text-[#314158]/70 mt-0.5 line-clamp-2">{tool.one_line}</p>
          </div>
          {tool.difficulty && (
            <span className={`text-[10px] px-2 py-0.5 rounded-full shrink-0 font-medium ${difficultyColor}`}>
              {tool.difficulty}
            </span>
          )}
        </div>

        {/* Tags */}
        {tool.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {tool.tags.map(tag => (
              <span key={tag} className="text-[10px] bg-[#B1CBF5]/20 text-[#314158]/70 px-1.5 py-0.5 rounded">
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Reason (from reranker) */}
        {tool.reason && (
          <p className="text-[11px] text-[#314158]/60 mt-2 italic">
            &quot;{tool.reason}&quot;
          </p>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2 mt-3">
          <a
            href={tool.github_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] font-medium text-blue-600 hover:text-blue-700 transition"
          >
            View on GitHub &rarr;
          </a>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] text-[#314158]/50 hover:text-[#314158]/80 transition ml-auto"
          >
            {expanded ? "Less" : "More"}
          </button>
          {onAsk && (
            <button
              onClick={() => onAsk(`Tell me more about ${tool.tool_name}`)}
              className="text-[11px] text-[#314158]/50 hover:text-[#314158]/80 transition"
            >
              Ask about this
            </button>
          )}
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-3 border-t border-[#B1CBF5]/20 pt-2">
          {tool.use_cases.length > 0 && (
            <div className="mb-2">
              <p className="text-[10px] font-semibold text-[#314158]/50 uppercase tracking-wide mb-1">Use cases</p>
              <ul className="text-xs text-[#314158]/70 space-y-0.5">
                {tool.use_cases.map((uc, i) => (
                  <li key={i}>- {uc}</li>
                ))}
              </ul>
            </div>
          )}
          {tool.readme_preview && (
            <div>
              <p className="text-[10px] font-semibold text-[#314158]/50 uppercase tracking-wide mb-1">README preview</p>
              <p className="text-[11px] text-[#314158]/60 leading-relaxed line-clamp-4">{tool.readme_preview}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
