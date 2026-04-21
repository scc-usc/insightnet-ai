// Password gate removed — auth is handled by Firebase anonymous sign-in.
export const dynamic = "force-static"

export async function GET() {
  return new Response(null, { status: 204 })
}
