// Plan vs actual (Etsy › Ornament): pieces, gap, % of plan bars — shared by the product type and account tables.
import { num } from './format'

/** Pieces, rounded: 1326.9 → "1,327". */
export const pcs = (v: number | null | undefined) => (v == null ? '—' : num(Math.round(v)))

/** Pieces sold minus the plan to date as shown (rounded), so the gap is exactly the difference of the two cells. */
export function gapOf(r: { total_quantity: number; plan?: number | null }): number | undefined {
  return r.plan == null ? undefined : r.total_quantity - Math.round(r.plan)
}

/** "+12", "−219", "0"; empty without a plan. */
export function signedPcs(v: number | null | undefined): string {
  if (v == null) return ''
  const n = Math.round(v)
  return (n > 0 ? '+' : n < 0 ? '−' : '') + num(Math.abs(n))
}

export const gapClass = (v: number | null | undefined) => (v == null || Math.round(v) === 0 ? '' : v < 0 ? 'text-red-600' : 'text-green-600')
/** The same as a colour, where a utility class would lose to a component style (KPI values). */
export const gapColor = (v: number | null | undefined) => (v == null || Math.round(v) === 0 ? undefined : v < 0 ? '#dc2626' : '#16a34a')

/** Width of a % of plan bar (capped at 100) and its colour: green from 100 %, amber from 80 %, red below. */
export const bar = (r: number | null | undefined) => (r == null ? 0 : Math.min(100, Math.round(r * 100)))
export const barColor = (r: number | null | undefined) => (r == null ? '#cbd5e1' : r >= 1 ? '#16a34a' : r >= 0.8 ? '#f59e0b' : '#ef4444')
