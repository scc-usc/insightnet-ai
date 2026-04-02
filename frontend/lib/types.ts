export type ToolCard = {
  rank: number
  repo_name: string
  tool_name: string
  one_line: string
  reason: string
  tags: string[]
  difficulty: string
  use_cases: string[]
  github_url: string
  readme_preview: string
  score: number
}

export type Message = {
  id: string
  role: "user" | "assistant"
  content: string
  followups?: string[]
  tools?: ToolCard[]
  status?: string
}
