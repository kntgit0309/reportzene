export type Role = 'member' | 'admin'
export type User = { id: number; email: string; name: string; code: string; role: Role; is_active: boolean; avatar_url: string | null; is_pod: boolean
  scope_sellers: string[] } // trackingis seller ids a member sees only (their own sales); [] = the whole of ZenE

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
export type FamilyKey = 'ornament' | 'shirt' | 'blanket' | 'quilted' | 'flag' | 'wooden_block' | 'badge_reel' | 'others'
export type FamilyLine = {
  name: string; total_order: number; total_quantity: number; total_revenue: number; total: number; sale_tax: number
  avg_order_value: number; share: number | null
  fix_quantity?: number // pieces trackingis misses, added by hand (already inside total_quantity)
  plan?: number // planned pieces for the date range (months pro rata), product types and total only
  plan_month?: number // planned pieces of the whole months the range touches
  achieved?: number | null // total_quantity / plan
  pl2_per_item?: number | null // product types and the total: the business plan's PL2 per item (none for Others' total)
  pl2_est?: number | null // PL2 theo KT: quantity × PL2/item; absent without the business plan
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
  family: { key: FamilyKey; name: string; sub_types: string[] } // every sub product type the page covers
  total: Omit<Totals, 'date_from' | 'date_to'> & Pick<FamilyLine, 'fix_quantity' | 'plan' | 'plan_month' | 'achieved' | 'pl2_per_item' | 'pl2_est'>
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
  pl2_est?: number | null // PL2 theo KT: quantity × the business plan's PL2/item; absent without that plan
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

/** Etsy › Report, sales by product vs plan: a product of the business plan (Etsy › Plan) and its ZenE sales. */
export type OverviewLine = {
  total_order: number; total_quantity: number; total: number; sale_tax: number; total_revenue: number; avg_order_value: number
  plan?: number | null; plan_month?: number | null; achieved?: number | null // absent without a plan to compare with
  pl2_plan?: number | null; pl2_est?: number | null // PL2 of the plan for the range; quantity × the plan's PL2/item
  plan_quantity?: number; pl2_achieved?: number | null // the total only: pieces of the products with a plan line (achieved = that / plan); pl2_est / pl2_plan
  fix_quantity?: number // pieces trackingis misses, added by hand (Felt Ornament; already inside total_quantity)
}
export type OverviewRow = OverviewLine & {
  name: string; page: FamilyKey | null; sub_types: string[]; share: number | null; pl2_per_item?: number | null
}
export type Overview = {
  rows: OverviewRow[]
  total: OverviewLine
  plan: FamilyPlanInfo
  query: { date_from: string; date_to: string; teams: string[] }
}

/** Etsy › Report, PL2 KT vs CF: finance's monthly PL2 (CF) next to the PL2 estimated from sales (KT), per month. */
export type Pl2Figures = { // PL2 theo CF; gap = actual − plan_to_date, achieved = actual / plan_to_date
  plan: number | null; plan_to_date: number | null; actual: number | null; gap: number | null; achieved: number | null
}
export type Pl2Month = Partial<Pl2Figures> & {
  month: string; days: number; month_days: number
  kt: number | null // PL2 theo KT for the report's days of the month
  kt_minus_cf?: number | null
  teams?: (Pl2Figures & { team: string })[] // per-team CF lines, when the whole of ZenE is selected
}
export type Pl2Report = {
  months: Pl2Month[]
  total: Partial<Pl2Figures> & { kt: number | null; kt_minus_cf?: number | null }
  cf: { error?: string; sheet?: { id: number; name: string; tab_title: string; last_synced_at: string | null }; scope?: string }
  query: { date_from: string; date_to: string; teams: string[] }
}

/** PL2 per account: PL2 theo KT (quantity × the plan's PL2/item) and finance's PROFIT THỰC ĐẠT (PL2 theo CF); null = not available */
export type Pl2AccountLine = {
  shop: string; team: string | null; quantity: number; kt: number | null; cf: number | null; cf_minus_kt: number | null
  plan?: number | null // KH plan to date (pieces) of the account, over the KH sheets planning per store
}
type SheetRef = { id: number; name: string; tab_title: string; last_synced_at: string | null }
export type Pl2Accounts = {
  accounts: Pl2AccountLine[] // the accounts of the KH plan sheets, in sheet order
  others: Pl2AccountLine & { count: number; children: Pl2AccountLine[] } // accounts outside the plans with a PL2
  total: Pl2AccountLine
  kt: { error?: string }
  cf: { error?: string; sheet?: SheetRef; list?: SheetRef; months?: string[]; warnings?: string[] }
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
