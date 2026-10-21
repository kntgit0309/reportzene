// Plan vs actual (Etsy › Ornament, Etsy › Shirt): pieces, gap, % of plan bars — shared by the product type and account tables.
import { h, type VNode } from 'vue'
import { num } from './format'

/** Calendar days of a date range, both ends included: 2026-10-01 → 2026-10-19 is 19 days. */
export function rangeDays(from: string, to: string): number {
  const ms = Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)
  return Number.isFinite(ms) ? Math.max(1, Math.round(ms / 86_400_000) + 1) : 1
}

/** Avg sales/day (and KH avg/day): pieces per day of the range, rounded to whole pieces ("100"). */
export const perDay = (pcs: number | null | undefined, days: number) => (pcs == null ? '—' : num(Math.round(pcs / days)))
/** The same, unformatted (CSV). */
export const perDayValue = (pcs: number | null | undefined, days: number) => (pcs == null ? '' : Math.round(pcs / days))

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
/** PL2 estimated from sales (PL2 theo KT) in charts. */
export const KT_COLOR = '#0d9488'
/** Finance's PL2 actual (PL2 theo CF): blue to stand out, red when negative (KPI values, table cells and totals). */
export const CF_COLOR = '#2563eb'
export const cfColor = (v: number | null | undefined) => (v != null && Math.round(v * 100) < 0 ? '#dc2626' : CF_COLOR)
/** A CF figure in a table total row, coloured like the cells (summary-method cells are plain text otherwise). */
export const cfTotal = (v: number | null | undefined, text: string): VNode => h('span', { style: { color: cfColor(v) } }, text)

/** Width of a % of plan bar (capped at 100) and its colour: green from 100 %, amber from 80 %, red below. */
export const bar = (r: number | null | undefined) => (r == null ? 0 : Math.min(100, Math.round(r * 100)))
export const barColor = (r: number | null | undefined) => (r == null ? '#cbd5e1' : r >= 1 ? '#16a34a' : r >= 0.8 ? '#f59e0b' : '#ef4444')
