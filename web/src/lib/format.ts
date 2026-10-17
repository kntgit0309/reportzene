const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 })
const int = new Intl.NumberFormat('en-US')
const dec1 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })

export const money = (v: number | null | undefined) => (v == null ? '—' : usd.format(v))
export const moneyRound = (v: number | null | undefined) => (v == null ? '—' : usd0.format(v))
export const num = (v: number | null | undefined) => (v == null ? '—' : int.format(v))
export const num1 = (v: number | null | undefined) => (v == null ? '—' : dec1.format(v))

/** Spreadsheet column name: 1 → A, 17 → Q, 27 → AA. */
export function columnLetter(n: number | null | undefined): string {
  let out = ''
  for (let i = n ?? 0; i > 0; i = Math.floor((i - 1) / 26)) out = String.fromCharCode(65 + ((i - 1) % 26)) + out
  return out
}
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
