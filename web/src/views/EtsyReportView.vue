<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import Pl2ByAccount from '../components/report/Pl2ByAccount.vue'
import Pl2BySeller from '../components/report/Pl2BySeller.vue'
import ProductCards from '../components/report/ProductCards.vue'
import Pl2Comparison from '../components/report/Pl2Comparison.vue'
import ProductOverview from '../components/report/ProductOverview.vue'
import ReportBreakdown from '../components/report/ReportBreakdown.vue'
import ReportFilters from '../components/report/ReportFilters.vue'
import { auth } from '../lib/auth'
import { money, num } from '../lib/format'
import { perDay, rangeDays } from '../lib/plan'
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

// the report is split in four parts: one tab each, the first one (Overview) is the page's default and is left out of the URL
const TABS = [{ value: 'overview', label: 'Overview' }, { value: 'account', label: 'Account' }, { value: 'product', label: 'Product' },
  { value: 'seller', label: 'Seller' }] as const
type Tab = (typeof TABS)[number]['value']
const tab = ref<Tab>(TABS.find((t) => t.value === route.query.tab)?.value ?? 'overview')

const breakdown = ref<InstanceType<typeof ReportBreakdown> | null>(null)
const overview = ref<InstanceType<typeof ProductOverview> | null>(null)
const pl2 = ref<InstanceType<typeof Pl2Comparison> | null>(null)
const pl2Accounts = ref<InstanceType<typeof Pl2ByAccount> | null>(null)
const pl2Sellers = ref<InstanceType<typeof Pl2BySeller> | null>(null)
const productCards = ref<InstanceType<typeof ProductCards> | null>(null)
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
  router.replace({ query: { tab: tab.value === 'overview' ? undefined : tab.value, view: view.value === 'date' ? undefined : view.value,
    from: applied.value.date_from, to: applied.value.date_to } })
}

function onTabChange() {
  syncUrl()
  // charts built while their tab was hidden (or sized before the window changed) have no width yet: Highcharts reflows on resize
  nextTick(() => window.dispatchEvent(new Event('resize')))
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
    { label: 'Avg sales/day', value: t ? perDay(t.total_quantity, rangeDays(applied.value.date_from, applied.value.date_to)) : '—' },
    { label: 'Avg order value', value: t ? money(t.avg_order_value) : '—' },
    { label: 'Total (incl. tax)', value: t ? money(t.total) : '—' },
    { label: 'Sale tax', value: t ? money(t.sale_tax) : '—' },
  ]
})
// seller version (a member limited to their own sales): their results, their share of the plan and their own CF
const seller = auth.ownSalesOnly
const subtitle = computed(() => `${seller.value ? 'Your own Etsy sales' : 'ZenE Etsy sales'} from trackingis · ${applied.value.date_from} → ${applied.value.date_to}`)

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
      <el-button :icon="Refresh" :loading="loadingTotals" @click="breakdown?.reload(); overview?.reload(); productCards?.reload(); pl2?.reload(); pl2Accounts?.reload(); pl2Sellers?.reload(); loadTotals()">Refresh</el-button>
      <el-button type="success" plain :icon="Download" :disabled="!rows.length" @click="exportCsv">Export</el-button>
    </template>
  </PageHeader>

  <ReportFilters v-model="filters" v-model:teams-touched="teamsTouched" :default-teams="defaultTeams" @apply="apply" @reset="reset" />

  <!-- The filters above apply to every part. Overview is always built (it feeds the filters' default teams and the export); the
       others are built, and ask trackingis, the first time their tab is opened, then stay. -->
  <el-tabs v-model="tab" class="report-tabs" @tab-change="onTabChange">
    <el-tab-pane :label="TABS[0].label" :name="TABS[0].value">
      <Pl2Comparison ref="pl2" :params="applied" />

      <div v-loading="loadingTotals" class="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <div v-for="k in kpis" :key="k.label" class="kpi">
          <div class="kpi__label">{{ k.label }}</div>
          <div class="kpi__value">{{ k.value }}</div>
        </div>
      </div>

      <ReportBreakdown ref="breakdown" :params="applied" :initial-view="initialView" @loaded="onLoaded" @view-change="onViewChange" />
    </el-tab-pane>

    <el-tab-pane :label="TABS[1].label" :name="TABS[1].value" lazy>
      <Pl2ByAccount ref="pl2Accounts" :params="applied" />
    </el-tab-pane>

    <el-tab-pane :label="TABS[2].label" :name="TABS[2].value" lazy>
      <ProductOverview ref="overview" :params="applied" />

      <ProductCards ref="productCards" :params="applied" />
    </el-tab-pane>

    <el-tab-pane :label="TABS[3].label" :name="TABS[3].value" lazy>
      <Pl2BySeller ref="pl2Sellers" :params="applied" />
    </el-tab-pane>
  </el-tabs>
</template>

<style scoped>
.report-tabs :deep(.el-tabs__header) {
  margin-bottom: 14px;
}
.report-tabs :deep(.el-tabs__item) {
  height: 44px;
  padding: 0 22px;
  font-size: 15px;
  font-weight: 600;
}
</style>
