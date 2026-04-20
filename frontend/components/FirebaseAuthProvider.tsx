"use client"

/**
 * FirebaseAuthProvider — calls ensureSignedIn() once on mount so that
 * the Firebase anonymous session is established before any API calls.
 * Renders children immediately (no loading gate needed for anonymous auth).
 */

import { useEffect } from "react"
import { ensureSignedIn } from "@/lib/firebase/auth"

export function FirebaseAuthProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    ensureSignedIn().catch(console.error)
  }, [])

  return <>{children}</>
}
