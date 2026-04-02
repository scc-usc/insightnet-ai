import { NextRequest, NextResponse } from "next/server"

export async function POST(request: NextRequest) {
  const { password } = await request.json()
  const sitePassword = process.env.SITE_PASSWORD

  if (!sitePassword) {
    // No password configured — allow access
    const res = NextResponse.json({ ok: true })
    res.cookies.set("insightnet-auth", "1", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 30, // 30 days
      path: "/",
    })
    return res
  }

  if (password === sitePassword) {
    const res = NextResponse.json({ ok: true })
    res.cookies.set("insightnet-auth", "1", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 30, // 30 days
      path: "/",
    })
    return res
  }

  return NextResponse.json({ error: "wrong password" }, { status: 401 })
}
