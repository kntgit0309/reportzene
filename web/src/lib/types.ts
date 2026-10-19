export type Role = 'member' | 'admin'
export type User = { id: number; email: string; name: string; code: string; role: Role; is_active: boolean; avatar_url: string | null; is_pod: boolean }

export type View = 'date' | 'order' | 'product' | 'store' | 'seller' | 'product_type'

/** One report row; which fields are present depends on the view. */
export type ReportRow = {
  id?: number | string
  date_at?: string
  shop_name?: string
  shop_id?: number
  seller_name?: string | null
  designer_name?: string | null
  product_name?: string
  product_type?: string | null
  image_url?: string | null
  listing_id?: number
  origin_id?: string
  order_id?: number
  currency?: string
  views?: number
  favorites?: number
  has_trademark?: number
  total_order?: number
  total_quantity?: number
  total?: number
  sale_tax?: number
  total_revenue?: number
  revenue?: number
  has_children?: boolean
  is_child?: boolean
  children?: ReportRow[]
  _key?: string
}

export type ReportPage = {
  rows: ReportRow[]
  paging: { page: number; per_page: number; total: number; last_page: number }
  query: { date_from: string; date_to: string; view: View; teams: string[] }
}

export type Totals = {
  total_order: number; total_quantity: number; total: number; sale_tax: number; total_revenue: number
  avg_order_value: number; days: number; date_from: string; date_to: string
}

/** Product family breakdown (Etsy › Ornament, Shirt, Blanket…): one line per product type, its sub product types as children. */
export type FamilyKey = 'ornament' | 'shirt' | 'blanket'
export type FamilyLine = {
  name: string; total_order: number; total_quantity: number; total_revenue: number; total: number; sale_tax: number
  avg_order_value: number; share: number | null
  fix_quantity?: number // pieces trackingis misses, added by hand (already inside total_quantity)
  plan?: number // planned pieces for the date range (months pro rata), product types and total only
  plan_month?: number // planned pieces of the whole months the range touches
  achieved?: number | null // total_quantity / plan
}
/** Where the family's plan comes from, or why there is none for these filters. */
export type FamilyPlanInfo = {
  error?: string
  sheet?: { id: number; name: string; tab_title: string; last_synced_at: string | null }
  scope?: string
  months?: { month: string; days: number; month_days: number }[]
  missing_months?: string[]
  shops?: number
}
export type FamilyMetric = 'total_revenue' | 'total_order' | 'total_quantity'
export type FamilyDay = { date_at: string; total_order: number; total_quantity: number; total_revenue: number }
// Sub product types have their own `daily` when the family is a single product type (the chart then stacks them)
export type FamilyGroup = FamilyLine & { children: (FamilyLine & { daily?: FamilyDay[] })[]; daily: FamilyDay[] }
export type FamilyReport = {
  family: { key: FamilyKey; name: string }
  total: Omit<Totals, 'date_from' | 'date_to'> & Pick<FamilyLine, 'fix_quantity' | 'plan' | 'plan_month' | 'achieved'>
  groups: FamilyGroup[]
  fix_note: string | null
  plan: FamilyPlanInfo
  query: { date_from: string; date_to: string; teams: string[] }
}

/** By account: a store's sales of the family (trackingis) next to its line of the family's plan (KH Ornament, KH Shirt). */
export type FamilyAccountLine = {
  name?: string // product type (sub product type for a single-type family), on the breakdown rows
  total_order: number; total_quantity: number; total: number; sale_tax: number; total_revenue: number; avg_order_value: number
  plan?: number | null; plan_month?: number | null; achieved?: number | null // absent when there is no plan to compare with
}
export type FamilyAccount = FamilyAccountLine & {
  shop: string; team: string | null; in_plan: boolean; children: FamilyAccountLine[]
  replaces: string[] // suspended stores whose plan line and sales this store took over (Settings › Plan)
}
export type AccountReplacement = { suspended: string; replacement: string }
export type FamilyAccountsReport = {
  accounts: FamilyAccount[]
  total: FamilyAccountLine
  plan: FamilyPlanInfo
  query: { date_from: string; date_to: string; teams: string[] }
}

export type Option = { id: number | string; name: string; parent_id?: number | null; type?: string }

export type Filters = {
  dateRange: [string, string]
  keyword: string
  shops: number[]
  sellers: number[]
  designers: number[]
  product_types: string[]
  sub_product_types: string[]
  teams: number[]
  total_order: string
  symbol: string
}

export type Sheet = {
  id: number; name: string; url: string; tab_id: string; tab_title: string; header_row: number; header: string[]
  row_count: number; last_error: string | null; last_synced_at: string | null
}
export type SheetTab = { sheet_id: string; title: string; rows: number }

/** One product of the plan (or the total); monthly lists follow `Plan.months`. */
export type PlanLine = {
  product: string; pl2_per_item: number | null; total_sales: number | null; total_pl2: number | null; share: number | null
  sales: (number | null)[]; sales_per_day: (number | null)[]; pl2: (number | null)[]
}
export type Plan = {
  sheet: Sheet; start_column: number; column_letter: string; max_products: number
  months: string[]; products: PlanLine[]; total: PlanLine
}
