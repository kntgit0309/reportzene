<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import OrnamentChart from '../components/report/OrnamentChart.vue'
import ReportFilters from '../components/report/ReportFilters.vue'
import { money, num, pct } from '../lib/format'
import { downloadCsv, emptyFilters, fetchOrnament, filterParams } from '../lib/report'
import type { Filters, OrnamentLine, OrnamentMetric, OrnamentReport } from '../lib/types'

type Row = OrnamentLine & { key: string; children?: Row[] }

const filters = ref<Filters>(emptyFilters())
const teamsTouched = ref(false)
const applied = ref<Record<string, string>>(filterParams(filters.value, false))
const data = ref<OrnamentReport | null>(null)
const defaultTeams = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const showChart = ref(true)
const metric = ref<OrnamentMetric>('total_revenue')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchOrnament(applied.value)
    if (!teamsTouched.value) defaultTeams.value = data.value.query.teams
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
  ...g, key: g.name, children: g.children.map((c) => ({ ...c, key: `${g.name}/${c.name}` })),
})))
const total = computed(() => data.value?.total)
const kpis = computed(() => {
  const t = total.value
  return [
    { label: 'Revenue', value: t ? money(t.total_revenue) : '—' },
    { label: 'Total orders', value: t ? num(t.total_order) : '—' },
    { label: 'Quantity', value: t ? num(t.total_quantity) : '—' },
    { label: 'Avg order value', value: t ? money(t.avg_order_value) : '—' },
    { label: 'Total (incl. tax)', value: t ? money(t.total) : '—' },
    { label: 'Sale tax', value: t ? money(t.sale_tax) : '—' },
  ]
})
const subtitle = computed(() => `ZenE ornament sales by product type · ${applied.value.date_from} → ${applied.value.date_to}`)

function rowClass({ row }: { row: Row }) {
  return row.children ? 'row-parent' : 'row-child'
}
/** Footer = all ornaments together (an order with several types counts once here). */
function footer(): string[] {
  const t = total.value
  return t ? ['All ornaments', num(t.total_order), num(t.total_quantity), money(t.total_revenue), money(t.avg_order_value), pct(1)] : []
}

function exportCsv() {
  const header = ['Product type', 'Sub product type', 'Total order', 'Quantity', 'Revenue', 'Avg order value', 'Share']
  const body = rows.value.flatMap((g) => [g, ...(g.children ?? [])].map((r) => [
    g.name, r === g ? '' : r.name, r.total_order, r.total_quantity, r.total_revenue, r.avg_order_value, r.share ?? '',
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
    </div>
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
      <el-table-column label="Quantity" prop="total_quantity" width="110" align="right" sortable>
        <template #default="{ row }"><span class="num">{{ num(row.total_quantity) }}</span></template>
      </el-table-column>
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
    <div class="mt-2 text-xs text-muted">
      Product types group trackingis sub product types (Wooden Garland is in Others). An order with ornaments of several types
      counts in each, so the rows can add up to a little more than the total.
    </div>
  </div>
</template>
