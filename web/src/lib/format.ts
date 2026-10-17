const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const int = new Intl.NumberFormat('en-US')

export const money = (v: number | null | undefined) => (v == null ? '—' : usd.format(v))
export const num = (v: number | null | undefined) => (v == null ? '—' : int.format(v))
export const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)
export const ratio = (v: number | null | undefined) => (v == null ? '—' : v.toFixed(2))

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)
  return d.toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export const wordCount = (s: string) => (s.trim() ? s.trim().split(/\s+/).length : 0)

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
