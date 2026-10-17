<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import ReportChart from '../components/report/ReportChart.vue'
import ReportFilters from '../components/report/ReportFilters.vue'
import ReportTable from '../components/report/ReportTable.vue'
import { money, num } from '../lib/format'
import { DEFAULT_SORT, downloadCsv, emptyFilters, fetchReport, fetchTotals, filterParams, rowLabel, VIEWS } from '../lib/report'
import type { Filters, ReportRow, Totals, View } from '../lib/types'

const PAGE_SIZES = [20, 50, 100, 200]
const route = useRoute()
const router = useRouter()

const initialView = VIEWS.some((v) => v.value === route.query.view) ? (route.query.view as View) : 'date'
const view = ref<View>(initialView)
const filters = ref<Filters>(emptyFilters())
if (typeof route.query.from === 'string' && typeof route.query.to === 'string') filters.value.dateRange = [route.query.from, route.query.to]
const teamsTouched = ref(false)
const applied = ref<Record<string, string>>(filterParams(filters.value, false))

const table = reactive({ page: 1, perPage: 50, sortBy: DEFAULT_SORT[initialView], sortOrder: 'desc' })
const rows = ref<ReportRow[]>([])
const total = ref(0)
const totals = ref<Totals | null>(null)
const defaultTeams = ref<string[]>([])
const loading = ref(false)
const loadingTotals = ref(false)
const error = ref('')
const showChart = ref(true)
const metric = ref<'total_revenue' | 'total_order' | 'total_quantity'>('total_revenue')

async function loadRows() {
  loading.value = true
  error.value = ''
  try {
    const page = await fetchReport({ ...applied.value, view: view.value, page: table.page, per_page: table.perPage,
      sort_by: table.sortBy || DEFAULT_SORT[view.value], sort_order: table.sortOrder || 'desc' })
    rows.value = page.rows
    total.value = page.paging.total
    if (!teamsTouched.value) defaultTeams.value = page.query.teams
  } catch (e) {
    rows.value = []
    total.value = 0
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

async function loadTotals() {
  loadingTotals.value = true
  try {
    totals.value = await fetchTotals(applied.value)
  } catch {
    totals.value = null // the table shows the error
  } finally {
    loadingTotals.value = false
  }
}

function syncUrl() {
  router.replace({ query: { view: view.value === 'date' ? undefined : view.value, from: applied.value.date_from, to: applied.value.date_to } })
}

function apply() {
  applied.value = filterParams(filters.value, teamsTouched.value)
  table.page = 1
  syncUrl()
  loadRows()
  loadTotals()
}
function reset() {
  filters.value = emptyFilters()
  teamsTouched.value = false
  apply()
}
function changeView(v: View) {
  view.value = v
  table.page = 1
  table.sortBy = DEFAULT_SORT[v]
  table.sortOrder = 'desc'
  syncUrl()
  loadRows()
}
function onSort(by: string, order: string) {
  table.sortBy = by || DEFAULT_SORT[view.value]
  table.sortOrder = order || 'desc'
  table.page = 1
  loadRows()
}

const kpis = computed(() => {
  const t = totals.value
  return [
    { label: 'Revenue', value: t ? money(t.total_revenue) : '—' },
    { label: 'Total orders', value: t ? num(t.total_order) : '—' },
    { label: 'Quantity', value: t ? num(t.total_quantity) : '—' },
    { label: 'Avg order value', value: t ? money(t.avg_order_value) : '—' },
    { label: 'Total (incl. tax)', value: t ? money(t.total) : '—' },
    { label: 'Sale tax', value: t ? money(t.sale_tax) : '—' },
  ]
})
const subtitle = computed(() => `ZenE Etsy sales from trackingis · ${applied.value.date_from} → ${applied.value.date_to}`)
const chartable = computed(() => view.value !== 'order' && view.value !== 'product' && rows.value.length > 0)

function exportCsv() {
  const header = ['Name', 'Store', 'Seller', 'Designer', 'Product type', 'Total order', 'Quantity', 'Total', 'Sale tax', 'Revenue']
  const body = rows.value.map((r) => [rowLabel(r, view.value), r.shop_name, r.seller_name, r.designer_name, r.product_type, r.total_order,
    r.total_quantity, r.total, r.sale_tax, r.total_revenue ?? r.revenue])
  downloadCsv(`report-etsy-${view.value}-${applied.value.date_from}_${applied.value.date_to}.csv`, header, body)
  ElMessage.success(`Exported ${body.length} rows (this page)`)
}

onMounted(() => {
  loadRows()
  loadTotals()
})
</script>

<template>
  <PageHeader :subtitle="subtitle">
    <template #actions>
      <el-button :icon="Refresh" :loading="loading" @click="loadRows(); loadTotals()">Refresh</el-button>
      <el-button type="success" plain :icon="Download" :disabled="!rows.length" @click="exportCsv">Export</el-button>
    </template>
  </PageHeader>

  <ReportFilters v-model="filters" v-model:teams-touched="teamsTouched" :default-teams="defaultTeams" @apply="apply" @reset="reset" />

  <div v-loading="loadingTotals" class="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
    <div v-for="k in kpis" :key="k.label" class="kpi">
      <div class="kpi__label">{{ k.label }}</div>
      <div class="kpi__value">{{ k.value }}</div>
    </div>
  </div>

  <div class="section-card">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <el-segmented :model-value="view" :options="VIEWS" class="segmented-tabs" @change="(v: View) => changeView(v)" />
      <div class="flex items-center gap-3">
        <el-select v-if="chartable && showChart" v-model="metric" size="small" class="!w-[130px]">
          <el-option label="Revenue" value="total_revenue" />
          <el-option label="Orders" value="total_order" />
          <el-option label="Quantity" value="total_quantity" />
        </el-select>
        <el-switch v-if="chartable" v-model="showChart" active-text="Chart" />
      </div>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!mb-3" />
    <ReportChart v-if="chartable && showChart" :rows="rows" :view="view" :metric="metric" class="mb-3" />

    <ReportTable :rows="rows" :view="view" :loading="loading" :params="applied" :sort-by="table.sortBy" :sort-order="table.sortOrder" @sort="onSort" />

    <div class="mt-3 flex justify-end">
      <el-pagination v-model:current-page="table.page" v-model:page-size="table.perPage" :page-sizes="PAGE_SIZES" :total="total" background
                     layout="total, sizes, prev, pager, next" @current-change="loadRows" @size-change="table.page = 1; loadRows()" />
    </div>
  </div>
</template>
