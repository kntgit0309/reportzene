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

export type Option = { id: number | string; name: string; parent_id?: number | null; type?: string }

export type Filters = {
  dateRange: [string, string]
  keyword: string
  shops: number[]
  sellers: number[]
  designers: number[]
  product_types: string[]
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
