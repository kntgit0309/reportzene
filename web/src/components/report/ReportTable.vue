<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { money, num } from '../../lib/format'
import { fetchReport, rowLabel } from '../../lib/report'
import type { ReportRow, View } from '../../lib/types'

const CHILD_PAGE = 100
const props = defineProps<{ rows: ReportRow[]; view: View; loading: boolean; params: Record<string, string>; sortBy: string; sortOrder: string }>()
const emit = defineEmits<{ sort: [by: string, order: string] }>()

const FIRST_COL: Record<View, string> = { date: 'Date', order: 'Order', product: 'Product', store: 'Store', seller: 'Seller', product_type: 'Product type' }
const withMoneyBreakdown = computed(() => ['date', 'store', 'order'].includes(props.view))
const isTree = computed(() => props.view === 'date' || props.view === 'store')

const data = computed<ReportRow[]>(() => props.rows.map((r, i) => ({
  ...r, _key: `${props.view}-${r.id ?? r.shop_id ?? r.date_at ?? r.listing_id ?? r.order_id ?? i}-${i}`,
  has_children: isTree.value && r.has_children !== false,
})))

// Date rows open into their stores, store rows into their days (same calls as the trackingis page)
async function load(row: ReportRow, _node: unknown, resolve: (rows: ReportRow[]) => void) {
  try {
    const child = props.view === 'date'
      ? await fetchReport({ ...props.params, view: 'store', date_from: row.date_at!, date_to: row.date_at!, per_page: CHILD_PAGE, sort_by: 'total_revenue', sort_order: 'desc' })
      : await fetchReport({ ...props.params, view: 'date', shops: String(row.shop_id), per_page: CHILD_PAGE, sort_by: 'date_at', sort_order: 'desc' })
    resolve(child.rows.map((c, i) => ({ ...c, _key: `${row._key}-c${i}`, is_child: true, has_children: false,
      date_at: props.view === 'date' ? c.shop_name : c.date_at, shop_name: props.view === 'store' ? c.date_at : c.shop_name })))
  } catch (e) {
    ElMessage.error((e as Error).message)
    resolve([])
  }
}

function onSort({ prop, order }: { prop: string | null; order: 'ascending' | 'descending' | null }) {
  if (!prop || !order) emit('sort', '', '')
  else emit('sort', prop, order === 'ascending' ? 'asc' : 'desc')
}
const defaultSort = computed(() => (props.sortBy ? { prop: props.sortBy, order: props.sortOrder === 'asc' ? 'ascending' : 'descending' } as const : undefined))
const rowClass = ({ row }: { row: ReportRow }) => (row.is_child ? 'row-child' : 'row-parent')

const SUM_FIELDS = ['total_order', 'total_quantity', 'total', 'sale_tax', 'total_revenue', 'revenue']
function summary({ columns }: { columns: { property?: string }[] }) {
  return columns.map((c, i) => {
    if (i === 0) return 'Page total'
    if (!c.property || !SUM_FIELDS.includes(c.property)) return ''
    const s = data.value.reduce((acc, r) => acc + Number((r as Record<string, unknown>)[c.property!] ?? 0), 0)
    return c.property.includes('order') || c.property.includes('quantity') ? num(s) : money(s)
  })
}
const tmTag = (r: ReportRow) => (r.has_trademark ? { type: 'danger' as const, text: 'TM' } : { type: 'success' as const, text: 'Safe' })
</script>

<template>
  <el-table :key="view" v-loading="loading" :data="data" row-key="_key" :lazy="isTree" :load="load" :tree-props="{ children: 'children', hasChildren: 'has_children' }"
            :row-class-name="rowClass" :default-sort="defaultSort" show-summary :summary-method="summary" sum-text="Page total"
            empty-text="No sales for these filters" class="w-full" @sort-change="onSort">
    <el-table-column v-if="view === 'product'" label="Image" width="76">
      <template #default="{ row }">
        <el-image v-if="row.image_url" :src="row.image_url" fit="cover" class="h-12 w-12 rounded-md" :preview-src-list="[row.image_url.replace('il_100x100', 'il_570xN')]" preview-teleported />
      </template>
    </el-table-column>

    <el-table-column :label="FIRST_COL[view]" :min-width="view === 'product' ? 320 : 240" :class-name="isTree ? 'tree-cell' : ''" :prop="view === 'date' || view === 'order' ? 'date_at' : undefined"
                     :sortable="view === 'date' ? 'custom' : false">
      <template #default="{ row }">
        <template v-if="view === 'product'">
          <div class="line-clamp-2 font-medium text-slate-900" :title="row.product_name">{{ row.product_name }}</div>
          <div class="text-xs text-muted">#{{ row.listing_id }}</div>
        </template>
        <template v-else-if="view === 'order'">
          <div class="font-medium text-slate-900">{{ row.origin_id }}</div>
          <div class="text-xs text-muted">{{ row.date_at }}</div>
        </template>
        <span v-else>{{ rowLabel(row, view) }}</span>
      </template>
    </el-table-column>

    <template v-if="view === 'product'">
      <el-table-column label="TM" width="80" align="center"><template #default="{ row }"><el-tag size="small" :type="tmTag(row).type">{{ tmTag(row).text }}</el-tag></template></el-table-column>
      <el-table-column label="Product type" prop="product_type" min-width="130" />
      <el-table-column label="Store" prop="shop_name" min-width="140" />
      <el-table-column label="Seller" prop="seller_name" min-width="130" />
      <el-table-column label="Designer" prop="designer_name" min-width="150" />
      <el-table-column label="View/Fav" width="100" align="right"><template #default="{ row }"><span class="num">{{ num(row.views) }} / {{ num(row.favorites) }}</span></template></el-table-column>
    </template>

    <template v-if="view !== 'order'">
      <el-table-column label="Total order" prop="total_order" width="120" align="right" sortable="custom"><template #default="{ row }"><span class="num">{{ num(row.total_order) }}</span></template></el-table-column>
      <el-table-column label="Quantity" prop="total_quantity" width="110" align="right" sortable="custom"><template #default="{ row }"><span class="num">{{ num(row.total_quantity) }}</span></template></el-table-column>
    </template>
    <template v-if="withMoneyBreakdown">
      <el-table-column label="Total" prop="total" width="130" align="right" sortable="custom"><template #default="{ row }"><span class="num">{{ money(row.total) }}</span></template></el-table-column>
      <el-table-column label="Sale tax" prop="sale_tax" width="120" align="right" sortable="custom"><template #default="{ row }"><span class="num">{{ money(row.sale_tax) }}</span></template></el-table-column>
    </template>
    <el-table-column v-if="view === 'order'" label="Revenue" prop="revenue" width="130" align="right">
      <template #default="{ row }"><span class="num font-semibold text-slate-900">{{ money(row.revenue) }}</span> <span v-if="row.currency && row.currency !== 'USD'" class="text-xs text-muted">{{ row.currency }}</span></template>
    </el-table-column>
    <el-table-column v-else label="Revenue" prop="total_revenue" width="140" align="right" sortable="custom">
      <template #default="{ row }"><span class="num font-semibold text-slate-900">{{ money(row.total_revenue) }}</span></template>
    </el-table-column>
  </el-table>
</template>
