// Fetch wrapper for the {data, paging, meta} envelope.
// Session lives in an httpOnly cookie set by the backend — no token in JS storage.

export type Paging = { page: number; per_page: number; total: number }
export type Envelope<T> = { data: T; paging?: Paging; meta: { message: string; code?: string; errors?: Record<string, string[]> } }

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string, public errors?: Record<string, string[]>) {
    super(message)
  }
}

// "View as": the id of the seller account the app is viewed as, kept for this tab only and sent on every request
const VIEW_AS_KEY = 'rzn.view_as'
export function viewAsId(): string | null {
  try { return sessionStorage.getItem(VIEW_AS_KEY) } catch { return null }
}
export function setViewAsId(id: number | null): void {
  try { if (id == null) sessionStorage.removeItem(VIEW_AS_KEY); else sessionStorage.setItem(VIEW_AS_KEY, String(id)) } catch { /* private window */ }
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<Envelope<T>> {
  const headers: Record<string, string> = {}
  const viewing = viewAsId()
  if (viewing) headers['X-View-As'] = viewing
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }

  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, { method, headers, body: payload, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'Cannot reach the server')
  }
  const json = (await res.json().catch(() => null)) as Envelope<T> | null
  if (!res.ok || !json) {
    if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('rzn:logout'))
    const errors = json?.meta.errors
    const detail = errors ? ' — ' + Object.entries(errors).map(([k, v]) => `${k}: ${v.join(', ')}`).join('; ') : ''
    throw new ApiError(res.status, (json?.meta.message ?? `Error ${res.status}`) + detail, json?.meta.code, errors)
  }
  return json
}

export const api = {
  get: <T>(p: string) => request<T>('GET', p),
  post: <T>(p: string, b?: unknown) => request<T>('POST', p, b),
  patch: <T>(p: string, b?: unknown) => request<T>('PATCH', p, b),
  put: <T>(p: string, b?: unknown) => request<T>('PUT', p, b),
  del: <T>(p: string) => request<T>('DELETE', p),
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const s = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') s.set(k, String(v))
  const out = s.toString()
  return out ? `?${out}` : ''
}
