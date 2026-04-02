export type Message = {
  id: string
  role: "user" | "assistant"
  content: string
  followups?: string[]
  status?: string
}
