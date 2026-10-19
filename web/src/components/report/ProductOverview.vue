<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import FamilyPlanChart from './FamilyPlanChart.vue'
import { auth } from '../../lib/auth'
import { dateTime, money, num, pct } from '../../lib/format'
import { bar, barColor, gapClass, gapColor, gapOf, pcs, signedPcs } from '../../lib/plan'
import { downloadCsv, fetchOverview } from '../../lib/report'
import type { Overview, OverviewRow } from '../../lib/types'

type Row = OverviewRow & { gap?: number }

// Etsy › Report: every product of the business plan (Etsy › Plan) with its sales, for the report's filters
const props = defineProps<{ params: Record<string, string> }>()
const data = ref<Overview | null>(null)
const loading = ref(false)
const error = ref('')
const showChart = ref(true)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchOverview(props.params)
  } catch (e) {
    data.value = null
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
watch(() => props.params, load)
onMounted(load)
defineExpose({ reload: load })

const plan = computed(() => data.value?.plan)
const hasPlan = computed(() => !!plan.value && !plan.value.error)
const rows = computed<Row[]>(() => (data.value?.rows ?? []).map((r) => ({ ...r, gap: gapOf(r) })))
const chartRows = computed(() => rows.value.filter((r) => r.plan || r.total_quantity))
const total = computed(() => data.value?.total)
const planSource = computed(() => {
  const p = plan.value
  if (!p || p.error) return ''
  const months = (p.months ?? []).map((m) => (m.days === m.month_days ? m.month : `${m.month} (${m.days}/${m.month_days} days)`))
  const missing = p.missing_months?.length ? ` · no plan for ${p.missing_months.join(', ')}` : ''
  return `${p.sheet?.name} · ${p.sheet?.tab_title} · ${p.scope} · ${months.join(', ')}${missing} · synced ${dateTime(p.sheet?.last_synced_at)}`
})
const planKpis = computed(() => {
  const t = total.value
  const gap = t ? gapOf(t) : undefined
  return [
    { label: 'Plan to date', value: pcs(t?.plan), hint: 'Pieces, months pro rata of the days in the range' },
    { label: 'Actual', value: pcs(t?.total_quantity), hint: t?.fix_quantity ? `Quantity sold, incl. +${num(t.fix_quantity)} added by hand` : 'Quantity sold, every product' },
    { label: 'Gap', value: signedPcs(gap) || '—', color: gapColor(gap), hint: 'Actual − Plan to date' },
    { label: '% of plan', value: pct(t?.achieved, 0), achieved: t?.achieved, color: barColor(t?.achieved) },
    { label: 'PL2 plan to date', value: money(t?.pl2_plan), hint: `Month plan ${pcs(t?.plan_month)} pcs` },
    { label: 'Est. PL2', value: money(t?.pl2_est), hint: 'Quantity × the plan\'s PL2/item' },
  ]
})

function footer(): string[] {
  const t = total.value
  if (!t) return []
  const planCells = hasPlan.value ? [pcs(t.plan), signedPcs(gapOf(t)), pct(t.achieved, 0), pcs(t.plan_month)] : []
  const pl2Cells = hasPlan.value ? ['', money(t.pl2_plan), money(t.pl2_est)] : []
  const quantity = num(t.total_quantity) + (t.fix_quantity ? ` (+${num(t.fix_quantity)})` : '')
  return ['All products', num(t.total_order), quantity, ...planCells, money(t.total_revenue), pct(1), ...pl2Cells]
}

function exportCsv() {
  const header = ['Product', 'Sub product types', 'Total order', 'Quantity', 'Plan to date', 'Gap', '% of plan', 'Month plan', 'Revenue',
    'Share', 'PL2/item', 'PL2 plan to date', 'Est. PL2']
  const body = rows.value.map((r) => [r.name, r.sub_types.join(' | '), r.total_order, r.total_quantity, r.plan ?? '',
    r.gap == null ? '' : Math.round(r.gap), r.achieved ?? '', r.plan_month ?? '', r.total_revenue, r.share ?? '', r.pl2_per_item ?? '',
    r.pl2_plan ?? '', r.pl2_est ?? ''])
  downloadCsv(`products-vs-plan-${props.params.date_from}_${props.params.date_to}.csv`, header, body)
  ElMessage.success(`Exported ${body.length} rows`)
}
</script>

<template>
  <div class="section-card">
    <div class="mb-1 flex flex-wrap items-center justify-between gap-3">
      <h3 class="card-title !mb-0">Sales by product vs plan</h3>
      <div class="flex items-center gap-3">
        <el-switch v-model="showChart" active-text="Chart" />
        <el-button size="small" type="success" plain :icon="Download" :disabled="!rows.length" @click="exportCsv">Export</el-button>
      </div>
    </div>
    <div v-if="hasPlan" class="mb-3 text-xs text-muted">{{ planSource }}</div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!my-3" />
    <el-alert v-else-if="data && !hasPlan" type="info" :closable="false" show-icon :title="plan?.error" class="!my-3">
      <RouterLink v-if="auth.isAdmin.value && plan?.error?.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
    </el-alert>

    <div v-if="hasPlan" v-loading="loading" class="mb-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <div v-for="k in planKpis" :key="k.label" class="kpi">
        <div class="kpi__label">{{ k.label }}</div>
        <div class="kpi__value" :style="k.color ? { color: k.color } : undefined">{{ k.value }}</div>
        <el-progress v-if="'achieved' in k" :percentage="bar(k.achieved)" :color="barColor(k.achieved)" :show-text="false" :stroke-width="6" class="mt-2" />
        <div v-else-if="k.hint" class="mt-1 text-xs text-muted">{{ k.hint }}</div>
      </div>
    </div>
    <FamilyPlanChart v-if="showChart && hasPlan && chartRows.length" :groups="chartRows" class="mb-3" />

    <el-table v-loading="loading" :data="rows" row-key="name" show-summary :summary-method="footer" empty-text="No sales for these filters"
              class="w-full">
      <el-table-column label="Product" min-width="170" fixed>
        <template #default="{ row }">
          <RouterLink v-if="row.page" :to="`/etsy/${row.page}`" class="font-medium text-[#2563eb]" :title="row.sub_types.join(', ')">
            {{ row.name }}
          </RouterLink>
          <span v-else :title="row.sub_types.join(', ')">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="Total order" prop="total_order" width="90" align="right" sortable>
        <template #default="{ row }"><span class="num">{{ num(row.total_order) }}</span></template>
      </el-table-column>
      <el-table-column label="Quantity" prop="total_quantity" width="110" align="right" sortable>
        <template #default="{ row }">
          <span class="num">{{ num(row.total_quantity) }}</span>
          <span v-if="row.fix_quantity" class="num text-xs text-amber-600" title="Pieces trackingis misses, added by hand"> (+{{ num(row.fix_quantity) }})</span>
        </template>
      </el-table-column>
      <template v-if="hasPlan">
        <el-table-column label="Plan to date" prop="plan" width="105" align="right" sortable>
          <template #default="{ row }"><span class="num">{{ row.plan == null ? '' : pcs(row.plan) }}</span></template>
        </el-table-column>
        <el-table-column label="Gap" prop="gap" width="90" align="right" sortable>
          <template #default="{ row }">
            <span class="num font-semibold" :class="gapClass(row.gap)" title="Quantity − Plan to date">{{ signedPcs(row.gap) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="% of plan" prop="achieved" width="120" sortable>
          <template #default="{ row }">
            <div v-if="row.plan" class="flex items-center gap-2">
              <el-progress :percentage="bar(row.achieved)" :color="barColor(row.achieved)" :show-text="false" :stroke-width="6" class="flex-1" />
              <span class="num w-11 text-right text-xs font-semibold" :style="{ color: barColor(row.achieved) }">{{ pct(row.achieved, 0) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Month plan" prop="plan_month" width="90" align="right">
          <template #default="{ row }"><span class="num text-muted">{{ row.plan_month == null ? '' : pcs(row.plan_month) }}</span></template>
        </el-table-column>
      </template>
      <el-table-column label="Revenue" prop="total_revenue" width="115" align="right" sortable>
        <template #default="{ row }"><span class="num font-semibold text-slate-900">{{ money(row.total_revenue) }}</span></template>
      </el-table-column>
      <el-table-column label="Share" prop="share" width="80" align="right">
        <template #default="{ row }"><span class="num">{{ pct(row.share) }}</span></template>
      </el-table-column>
      <template v-if="hasPlan">
        <el-table-column label="PL2/item" prop="pl2_per_item" width="80" align="right">
          <template #default="{ row }"><span class="num text-muted">{{ row.pl2_per_item == null ? '' : money(row.pl2_per_item) }}</span></template>
        </el-table-column>
        <el-table-column label="PL2 plan to date" prop="pl2_plan" width="120" align="right" sortable>
          <template #default="{ row }"><span class="num">{{ row.pl2_plan == null ? '' : money(row.pl2_plan) }}</span></template>
        </el-table-column>
        <el-table-column label="Est. PL2" prop="pl2_est" width="110" align="right" sortable>
          <template #default="{ row }"><span class="num font-semibold">{{ row.pl2_est == null ? '' : money(row.pl2_est) }}</span></template>
        </el-table-column>
      </template>
    </el-table>
    <div class="mt-2 text-xs text-muted">
      One row per product of the plan (Etsy › Plan), sold as the sub product types of its page — open a product for its details.
      Quilted is Quilted Laundry Basket, Tote Bag, Weekend Bag and Table Runner (no page of its own yet); Other products is every
      trackingis sub product type no product covers. An order with several products counts in each row, so the rows can add up to a
      little more than All products; sales without a sub product type in trackingis are only in the headline numbers above. Quantity
      includes the pieces a product page adds by hand (Felt Ornament), in the team-wide view.
      <template v-if="hasPlan">The plan is for ZenE as a whole. Est. PL2 = quantity × the plan's PL2/item.</template>
    </div>
  </div>
</template>
