/**
 * Firebase Auth helpers.
 *
 * signInAnonymously() is called once on app load. The resulting UID is
 * stable per browser (persists across page refreshes via IndexedDB).
 * getIdToken() returns a short-lived JWT (<1 h) that the backend verifies.
 *
 * Usage:
 *   import { ensureSignedIn, getIdToken } from "@/lib/firebase/auth"
 *
 *   // In a top-level component / layout:
 *   await ensureSignedIn()
 *
 *   // In API calls:
 *   const token = await getIdToken()
 *   fetch("/api/query", { headers: { Authorization: `Bearer ${token}` } })
 */

import { getAuth, signInAnonymously, onAuthStateChanged, User } from "firebase/auth"
import { firebaseApp } from "./client"

const auth = getAuth(firebaseApp)

let _user: User | null = null
let _initPromise: Promise<User | null> | null = null

/** Sign in anonymously if not already authenticated. Idempotent. */
export async function ensureSignedIn(): Promise<User | null> {
  if (_user) return _user

  if (!_initPromise) {
    _initPromise = new Promise((resolve) => {
      const unsub = onAuthStateChanged(auth, async (user) => {
        unsub()
        if (user) {
          _user = user
          resolve(user)
        } else {
          try {
            const cred = await signInAnonymously(auth)
            _user = cred.user
            resolve(cred.user)
          } catch (err) {
            console.error("Firebase anonymous sign-in failed:", err)
            resolve(null)
          }
        }
      })
    })
  }

  return _initPromise
}

/**
 * Get the current user's Firebase ID token.
 * Automatically refreshes if close to expiry (Firebase SDK handles this).
 * Returns null if not signed in.
 */
export async function getIdToken(): Promise<string | null> {
  const user = await ensureSignedIn()
  if (!user) return null
  return user.getIdToken(/* forceRefresh */ false)
}
