// Report Etsy: filters → query string for /report/etsy, date shortcuts, CSV export.
import { api } from './api'
import type { FamilyAccountsReport, FamilyKey, FamilyReport, Filters, Option, Overview, ReportPage, ReportRow, Totals, View } from './types'

export const VIEWS: { value: View; label: string }[] = [
  { value: 'date', label: 'Date' },
  { value: 'order', label: 'Order' },
  { value: 'product', label: 'Product' },
  { value: 'store', label: 'Store' },
  { value: 'seller', label: 'Seller' },
  { value: 'product_type', label: 'Product type' },
]
export const SYMBOLS = ['>', '>=', '=', '<=', '<']
export const DEFAULT_SORT: Record<View, string> = {
  date: 'date_at', order: 'date_at', product: 'total_revenue', store: 'total_revenue', seller: 'total_revenue', product_type: 'total_revenue',
}

const pad = (n: number) => String(n).padStart(2, '0')
export const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

/** Today in Vietnam time, whatever the browser's zone. */
export function vnToday(): Date {
  const s = new Date().toLocaleString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' })
  const [y, m, d] = s.split(',')[0].split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function shortcuts() {
  const t = vnToday()
  const day = (offset: number) => { const d = new Date(t); d.setDate(d.getDate() + offset); return d }
  const monthStart = new Date(t.getFullYear(), t.getMonth(), 1)
  const lastMonthStart = new Date(t.getFullYear(), t.getMonth() - 1, 1)
  const lastMonthEnd = new Date(t.getFullYear(), t.getMonth(), 0)
  return [
    { text: 'Today', value: () => [t, t] },
    { text: 'Yesterday', value: () => [day(-1), day(-1)] },
    { text: 'Last 7 days', value: () => [day(-6), t] },
    { text: 'Last 30 days', value: () => [day(-29), t] },
    { text: 'This month', value: () => [monthStart, t] },
    { text: 'Last month', value: () => [lastMonthStart, lastMonthEnd] },
  ]
}

export function emptyFilters(): Filters {
  const t = vnToday()
  return { dateRange: [ymd(new Date(t.getFullYear(), t.getMonth(), 1)), ymd(t)], keyword: '', shops: [], sellers: [], designers: [],
    product_types: [], sub_product_types: [], teams: [], total_order: '', symbol: '>=' }
}

/** Filters → query params. `teamsTouched` false = let the server apply the ZenE teams from Settings. */
export function filterParams(f: Filters, teamsTouched: boolean): Record<string, string> {
  const p: Record<string, string> = { date_from: f.dateRange[0], date_to: f.dateRange[1] }
  if (f.keyword.trim()) p.keyword = f.keyword.trim()
  for (const k of ['shops', 'sellers', 'designers', 'product_types', 'sub_product_types'] as const) if (f[k].length) p[k] = f[k].join(',')
  if (teamsTouched) p.teams = f.teams.join(',')
  if (f.total_order) { p.total_order = f.total_order; p.symbol = f.symbol || '=' }
  return p
}

const toQuery = (p: Record<string, string | number>) => '?' + new URLSearchParams(Object.entries(p).map(([k, v]) => [k, String(v)])).toString()

export const fetchReport = (p: Record<string, string | number>) => api.get<ReportPage>(`/report/etsy${toQuery(p)}`).then((r) => r.data)
export const fetchTotals = (p: Record<string, string | number>) => api.get<Totals>(`/report/etsy/totals${toQuery(p)}`).then((r) => r.data)
export const fetchOverview = (p: Record<string, string | number>) => api.get<Overview>(`/report/etsy/overview${toQuery(p)}`).then((r) => r.data)
export const fetchFamily = (family: FamilyKey, p: Record<string, string | number>) =>
  api.get<FamilyReport>(`/report/etsy/${family}${toQuery(p)}`).then((r) => r.data)
export const fetchFamilyAccounts = (family: FamilyKey, p: Record<string, string | number>) =>
  api.get<FamilyAccountsReport>(`/report/etsy/${family}/accounts${toQuery(p)}`).then((r) => r.data)

const optionCache = new Map<string, Promise<Option[]>>()
export function fetchOptions(kind: string): Promise<Option[]> {
  if (!optionCache.has(kind)) {
    optionCache.set(kind, api.get<Option[]>(`/report/etsy/options/${kind}`).then((r) => r.data).catch((e) => { optionCache.delete(kind); throw e }))
  }
  return optionCache.get(kind)!
}

/** Label shown in the first column of a row, whatever the view. */
export function rowLabel(r: ReportRow, view: View): string {
  if (view === 'date') return r.date_at ?? ''
  if (view === 'store') return r.shop_name ?? ''
  if (view === 'seller') return r.seller_name ?? '(no seller)'
  if (view === 'product_type') return r.product_type ?? '(no type)'
  if (view === 'order') return r.origin_id ?? String(r.order_id ?? '')
  return r.product_name ?? ''
}

export function downloadCsv(name: string, header: string[], rows: (string | number | null | undefined)[][]) {
  const esc = (v: string | number | null | undefined) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const body = [header, ...rows].map((r) => r.map(esc).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob(['﻿' + body], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  URL.revokeObjectURL(url)
}
