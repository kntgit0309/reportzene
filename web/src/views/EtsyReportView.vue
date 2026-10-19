<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import Pl2Comparison from '../components/report/Pl2Comparison.vue'
import ProductOverview from '../components/report/ProductOverview.vue'
import ReportBreakdown from '../components/report/ReportBreakdown.vue'
import ReportFilters from '../components/report/ReportFilters.vue'
import { money, num } from '../lib/format'
import { downloadCsv, emptyFilters, fetchTotals, filterParams, rowLabel, VIEWS } from '../lib/report'
import type { Filters, ReportPage, ReportRow, Totals, View } from '../lib/types'

const route = useRoute()
const router = useRouter()

const initialView = VIEWS.some((v) => v.value === route.query.view) ? (route.query.view as View) : 'date'
const view = ref<View>(initialView)
const filters = ref<Filters>(emptyFilters())
if (typeof route.query.from === 'string' && typeof route.query.to === 'string') filters.value.dateRange = [route.query.from, route.query.to]
const teamsTouched = ref(false)
const applied = ref<Record<string, string>>(filterParams(filters.value, false))

const breakdown = ref<InstanceType<typeof ReportBreakdown> | null>(null)
const overview = ref<InstanceType<typeof ProductOverview> | null>(null)
const pl2 = ref<InstanceType<typeof Pl2Comparison> | null>(null)
const rows = ref<ReportRow[]>([]) // the page the breakdown shows, for the export
const totals = ref<Totals | null>(null)
const defaultTeams = ref<string[]>([])
const loadingTotals = ref(false)

function onLoaded(page: ReportPage) {
  rows.value = page.rows
  if (!teamsTouched.value) defaultTeams.value = page.query.teams
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
  applied.value = filterParams(filters.value, teamsTouched.value) // a new object: the breakdown reloads from page 1
  syncUrl()
  loadTotals()
}
function reset() {
  filters.value = emptyFilters()
  teamsTouched.value = false
  apply()
}
function onViewChange(v: View) {
  view.value = v
  syncUrl()
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

function exportCsv() {
  const header = ['Name', 'Store', 'Seller', 'Designer', 'Product type', 'Total order', 'Quantity', 'Total', 'Sale tax', 'Revenue']
  const body = rows.value.map((r) => [rowLabel(r, view.value), r.shop_name, r.seller_name, r.designer_name, r.product_type, r.total_order,
    r.total_quantity, r.total, r.sale_tax, r.total_revenue ?? r.revenue])
  downloadCsv(`report-etsy-${view.value}-${applied.value.date_from}_${applied.value.date_to}.csv`, header, body)
  ElMessage.success(`Exported ${body.length} rows (this page)`)
}

onMounted(loadTotals)
</script>

<template>
  <PageHeader :subtitle="subtitle">
    <template #actions>
      <el-button :icon="Refresh" :loading="loadingTotals" @click="breakdown?.reload(); overview?.reload(); pl2?.reload(); loadTotals()">Refresh</el-button>
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

  <ProductOverview ref="overview" :params="applied" />

  <Pl2Comparison ref="pl2" :params="applied" />

  <ReportBreakdown ref="breakdown" :params="applied" :initial-view="initialView" @loaded="onLoaded" @view-change="onViewChange" />
</template>
