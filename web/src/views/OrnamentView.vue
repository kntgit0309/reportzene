<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import OrnamentAccounts from '../components/report/OrnamentAccounts.vue'
import OrnamentChart from '../components/report/OrnamentChart.vue'
import OrnamentPlanChart from '../components/report/OrnamentPlanChart.vue'
import ReportBreakdown from '../components/report/ReportBreakdown.vue'
import ReportFilters from '../components/report/ReportFilters.vue'
import { auth } from '../lib/auth'
import { dateTime, money, num, pct } from '../lib/format'
import { bar, barColor, gapClass, gapColor, gapOf, pcs, signedPcs } from '../lib/plan'
import { downloadCsv, emptyFilters, fetchOrnament, fetchOrnamentAccounts, filterParams } from '../lib/report'
import type { Filters, OrnamentAccountsReport, OrnamentLine, OrnamentMetric, OrnamentReport } from '../lib/types'

type Row = OrnamentLine & { key: string; gap?: number; children?: Row[] }

const filters = ref<Filters>(emptyFilters())
const teamsTouched = ref(false)
const applied = ref<Record<string, string>>(filterParams(filters.value, false))
const data = ref<OrnamentReport | null>(null)
const defaultTeams = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const showChart = ref(true)
const metric = ref<OrnamentMetric>('total_revenue')
// The report's views (date, store, seller…) for the same filters, restricted to the ornament sub product types
const breakdownParams = ref<Record<string, string> | null>(null)
// Per store (account) against the store's line of the plan: its own request, loaded alongside
const accounts = ref<OrnamentAccountsReport | null>(null)
const accountsLoading = ref(false)
const accountsError = ref('')

async function loadAccounts() {
  accountsLoading.value = true
  accountsError.value = ''
  try {
    accounts.value = await fetchOrnamentAccounts(applied.value)
  } catch (e) {
    accounts.value = null
    accountsError.value = (e as Error).message
  } finally {
    accountsLoading.value = false
  }
}
async function load() {
  loading.value = true
  error.value = ''
  loadAccounts()
  try {
    data.value = await fetchOrnament(applied.value)
    if (!teamsTouched.value) defaultTeams.value = data.value.query.teams
    const subs = data.value.groups.flatMap((g) => g.children.map((c) => c.name))
    breakdownParams.value = { ...applied.value, sub_product_types: subs.join(',') }
  } catch (e) {
    data.value = null
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
function apply() {
  applied.value = filterParams(filters.value, teamsTouched.value)
  load()
}
function reset() {
  filters.value = emptyFilters()
  teamsTouched.value = false
  apply()
}
onMounted(load)

const rows = computed<Row[]>(() => (data.value?.groups ?? []).map((g) => ({
  ...g, key: g.name, gap: gapOf(g), children: g.children.map((c) => ({ ...c, key: `${g.name}/${c.name}` })),
})))
const total = computed(() => data.value?.total)
const kpis = computed(() => {
  const t = total.value
  return [
    { label: 'Revenue', value: t ? money(t.total_revenue) : '—' },
    { label: 'Total orders', value: t ? num(t.total_order) : '—' },
    { label: 'Quantity', value: t ? num(t.total_quantity) : '—', hint: t?.fix_quantity ? `incl. +${num(t.fix_quantity)} pcs added by hand` : '' },
    { label: 'Avg order value', value: t ? money(t.avg_order_value) : '—' },
    { label: 'Total (incl. tax)', value: t ? money(t.total) : '—' },
    { label: 'Sale tax', value: t ? money(t.sale_tax) : '—' },
  ]
})
const subtitle = computed(() => `ZenE ornament sales by product type · ${applied.value.date_from} → ${applied.value.date_to}`)

// --- plan (sheet "KH Ornament"): pieces, compared with the quantity sold ---
const plan = computed(() => data.value?.plan)
const hasPlan = computed(() => !!plan.value && !plan.value.error)
const planSource = computed(() => {
  const p = plan.value
  if (!p || p.error) return ''
  const months = (p.months ?? []).map((m) => (m.days === m.month_days ? m.month : `${m.month} (${m.days}/${m.month_days} days)`))
  const missing = p.missing_months?.length ? ` · no plan for ${p.missing_months.join(', ')}` : ''
  return `${p.sheet?.name} · ${p.scope} · ${months.join(', ')}${missing} · synced ${dateTime(p.sheet?.last_synced_at)}`
})
const planKpis = computed(() => {
  const t = total.value
  const left = t?.plan_month != null ? Math.max(0, t.plan_month - t.total_quantity) : null
  const gap = t ? gapOf(t) : undefined
  return [
    { label: 'Plan to date', value: pcs(t?.plan), hint: 'Months pro rata of the days in the range' },
    { label: 'Actual', value: pcs(t?.total_quantity), hint: t?.fix_quantity ? `incl. +${num(t.fix_quantity)} added by hand` : 'Quantity sold' },
    { label: 'Gap', value: signedPcs(gap) || '—', color: gapColor(gap),
      hint: `Actual − Plan to date${gap == null || Math.round(gap) === 0 ? '' : gap < 0 ? ': behind plan' : ': ahead of plan'}` },
    { label: '% of plan', value: pct(t?.achieved, 0), achieved: t?.achieved, color: barColor(t?.achieved) },
    { label: 'Month plan', value: pcs(t?.plan_month), hint: left == null ? '' : `${pcs(left)} pcs still to sell` },
  ]
})

function rowClass({ row }: { row: Row }) {
  return row.children ? 'row-parent' : 'row-child'
}
/** Footer = all ornaments together (an order with several types counts once here). */
function footer(): string[] {
  const t = total.value
  if (!t) return []
  const planCells = hasPlan.value ? [pcs(t.plan), signedPcs(gapOf(t)), pct(t.achieved, 0), pcs(t.plan_month)] : []
  return ['All ornaments', num(t.total_order), quantity(t), ...planCells, money(t.total_revenue), money(t.avg_order_value), pct(1)]
}
/** Quantity with the pieces added by hand shown next to it, e.g. "390 (+170)". */
const quantity = (r: { total_quantity: number; fix_quantity?: number }) =>
  num(r.total_quantity) + (r.fix_quantity ? ` (+${num(r.fix_quantity)})` : '')

function exportCsv() {
  const header = ['Product type', 'Sub product type', 'Total order', 'Quantity', 'Quantity added by hand', 'Plan to date', 'Gap', '% of plan',
    'Month plan', 'Revenue', 'Avg order value', 'Share']
  const body = rows.value.flatMap((g) => [g, ...(g.children ?? [])].map((r) => [
    g.name, r === g ? '' : r.name, r.total_order, r.total_quantity, r.fix_quantity ?? '', r.plan ?? '', r.gap == null ? '' : Math.round(r.gap),
    r.achieved ?? '', r.plan_month ?? '',
    r.total_revenue, r.avg_order_value, r.share ?? '',
  ]))
  downloadCsv(`ornament-${applied.value.date_from}_${applied.value.date_to}.csv`, header, body)
  ElMessage.success(`Exported ${body.length} rows`)
}
</script>

<template>
  <PageHeader :subtitle="subtitle">
    <template #actions>
      <el-button :icon="Refresh" :loading="loading" @click="load">Refresh</el-button>
      <el-button type="success" plain :icon="Download" :disabled="!rows.length" @click="exportCsv">Export</el-button>
    </template>
  </PageHeader>

  <ReportFilters v-model="filters" v-model:teams-touched="teamsTouched" :default-teams="defaultTeams"
                 :hide="['product_types', 'sub_product_types', 'total_order']" @apply="apply" @reset="reset" />

  <div v-loading="loading" class="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
    <div v-for="k in kpis" :key="k.label" class="kpi">
      <div class="kpi__label">{{ k.label }}</div>
      <div class="kpi__value">{{ k.value }}</div>
      <div v-if="k.hint" class="mt-1 text-xs text-amber-600">{{ k.hint }}</div>
    </div>
  </div>

  <div v-if="data" class="section-card">
    <h3 class="card-title !mb-1">Actual vs plan (pieces)</h3>
    <div v-if="hasPlan" class="mb-3 text-xs text-muted">{{ planSource }}</div>
    <el-alert v-if="!hasPlan" type="info" :closable="false" show-icon :title="plan?.error" class="!mt-2">
      <RouterLink v-if="auth.isAdmin.value && plan?.error?.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
    </el-alert>
    <template v-else>
      <div class="mb-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <div v-for="k in planKpis" :key="k.label" class="kpi">
          <div class="kpi__label">{{ k.label }}</div>
          <div class="kpi__value" :style="k.color ? { color: k.color } : undefined">{{ k.value }}</div>
          <el-progress v-if="'achieved' in k" :percentage="bar(k.achieved)" :color="barColor(k.achieved)" :show-text="false" :stroke-width="6" class="mt-2" />
          <div v-else-if="k.hint" class="mt-1 text-xs text-muted">{{ k.hint }}</div>
        </div>
      </div>
      <OrnamentPlanChart :groups="data.groups" />
    </template>
  </div>

  <div class="section-card">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <h3 class="card-title !mb-0">Ornament by product type</h3>
      <div class="flex items-center gap-3">
        <el-select v-if="showChart" v-model="metric" size="small" class="!w-[130px]">
          <el-option label="Revenue" value="total_revenue" />
          <el-option label="Orders" value="total_order" />
          <el-option label="Quantity" value="total_quantity" />
        </el-select>
        <el-switch v-model="showChart" active-text="Chart" />
      </div>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!mb-3" />
    <OrnamentChart v-if="showChart && data" :groups="data.groups" :metric="metric" class="mb-3" />

    <el-table v-loading="loading" :data="rows" row-key="key" :tree-props="{ children: 'children' }" :row-class-name="rowClass"
              show-summary :summary-method="footer" empty-text="No ornament sales for these filters" class="w-full">
      <el-table-column label="Product type / Sub product type" min-width="260" class-name="tree-cell">
        <template #default="{ row }">{{ row.name }}</template>
      </el-table-column>
      <el-table-column label="Total order" prop="total_order" width="120" align="right" sortable>
        <template #default="{ row }"><span class="num">{{ num(row.total_order) }}</span></template>
      </el-table-column>
      <el-table-column label="Quantity" prop="total_quantity" width="130" align="right" sortable>
        <template #default="{ row }">
          <span class="num">{{ num(row.total_quantity) }}</span>
          <span v-if="row.fix_quantity" class="num text-xs text-amber-600" title="Pieces trackingis misses, added by hand"> (+{{ num(row.fix_quantity) }})</span>
        </template>
      </el-table-column>
      <template v-if="hasPlan">
        <el-table-column label="Plan to date" prop="plan" width="115" align="right" sortable>
          <template #default="{ row }"><span class="num">{{ row.plan == null ? '' : pcs(row.plan) }}</span></template>
        </el-table-column>
        <el-table-column label="Gap" prop="gap" width="100" align="right" sortable>
          <template #default="{ row }">
            <span class="num font-semibold" :class="gapClass(row.gap)" title="Quantity − Plan to date">{{ signedPcs(row.gap) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="% of plan" prop="achieved" width="150" sortable>
          <template #default="{ row }">
            <div v-if="row.plan != null" class="flex items-center gap-2">
              <el-progress :percentage="bar(row.achieved)" :color="barColor(row.achieved)" :show-text="false" :stroke-width="6" class="flex-1" />
              <span class="num w-11 text-right text-xs font-semibold" :style="{ color: barColor(row.achieved) }">{{ pct(row.achieved, 0) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Month plan" prop="plan_month" width="110" align="right">
          <template #default="{ row }"><span class="num text-muted">{{ row.plan_month == null ? '' : pcs(row.plan_month) }}</span></template>
        </el-table-column>
      </template>
      <el-table-column label="Revenue" prop="total_revenue" width="140" align="right" sortable>
        <template #default="{ row }"><span class="num font-semibold text-slate-900">{{ money(row.total_revenue) }}</span></template>
      </el-table-column>
      <el-table-column label="Avg order value" prop="avg_order_value" width="140" align="right">
        <template #default="{ row }"><span class="num">{{ money(row.avg_order_value) }}</span></template>
      </el-table-column>
      <el-table-column label="Share of revenue" prop="share" width="140" align="right">
        <template #default="{ row }"><span class="num">{{ pct(row.share) }}</span></template>
      </el-table-column>
    </el-table>
    <div v-if="data?.fix_note" class="mt-2 text-xs text-amber-600">Quantity {{ data.fix_note }}.</div>
    <div class="mt-2 text-xs text-muted">
      Product types group trackingis sub product types (Wooden Garland is in Others). An order with ornaments of several types
      counts in each, so the rows can add up to a little more than the total.
      <template v-if="hasPlan">Plan: Acrylic and Wood together are Acrylic + Wood, "Ornament khác" is Others. Gap = Quantity − Plan to date.</template>
    </div>
  </div>

  <OrnamentAccounts :report="accounts" :loading="accountsLoading" :error="accountsError" :date-from="applied.date_from" :date-to="applied.date_to" />

  <ReportBreakdown v-if="breakdownParams" :params="breakdownParams" title="Ornament by date, order, product, store, seller and product type">
    <div class="mt-2 text-xs text-muted">
      Same views as Report, for every ornament sub product type above, straight from trackingis
      <template v-if="data?.fix_note">(without the Felt pieces added by hand)</template>.
    </div>
  </ReportBreakdown>
</template>
