"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Image from "next/image"

export default function LoginPage() {
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!password.trim()) return

    setLoading(true)
    setError("")

    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      })

      if (res.ok) {
        router.push("/")
        router.refresh()
      } else {
        setError("Incorrect password")
      }
    } catch {
      setError("Something went wrong")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white/50 backdrop-blur-sm rounded-2xl shadow-xl p-8">
        <div className="text-center mb-6">
          <Image src="/logo.png" alt="Logo" width={48} height={48} className="mx-auto mb-3 opacity-80" />
          <h1 className="text-xl font-bold text-[#1b183c]">Insight Net</h1>
          <p className="text-sm text-[#314158]/60 mt-1">Enter the password to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
            className="w-full text-sm outline-none text-black bg-white rounded-lg px-4 py-3 shadow-sm border border-white/40 placeholder:text-[#314158]/40"
          />

          {error && (
            <p className="text-xs text-red-500 text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !password.trim()}
            className="w-full py-3 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
          >
            {loading ? "Checking..." : "Enter"}
          </button>
        </form>
      </div>
    </main>
  )
}
