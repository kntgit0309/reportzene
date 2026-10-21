<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Link, Refresh } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import PlanChart from '../components/plan/PlanChart.vue'
import { api } from '../lib/api'
import { auth } from '../lib/auth'
import { dateTime, money, moneyRound, num, pct } from '../lib/format'
import { pcs } from '../lib/plan'
import type { Plan } from '../lib/types'

const plan = ref<Plan | null>(null)
const loading = ref(false)
const syncing = ref(false)
const error = ref('')
const showChart = ref(true)
const metric = ref<'pl2' | 'sales'>('pl2')

async function load() {
  loading.value = true
  error.value = ''
  try {
    plan.value = (await api.get<Plan>('/plan/products')).data
  } catch (e) {
    plan.value = null
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function sync() {
  if (!plan.value) return
  syncing.value = true
  try {
    const res = await api.post(`/sheets/${plan.value.sheet.id}/sync`)
    ElMessage.success(res.meta.message)
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    syncing.value = false
  }
}

const subtitle = computed(() => {
  const p = plan.value
  if (!p) return 'ZenE Etsy plan per product, from the plan sheet in Lark › Team sheets'
  return `${p.sheet.name} · ${p.sheet.tab_title} · from column ${p.column_letter} · synced ${dateTime(p.sheet.last_synced_at)}`
})

const kpis = computed(() => {
  const t = plan.value?.total
  return [
    { label: 'Total sales', value: num(t?.total_sales), hint: `${plan.value?.products.length ?? 0} products` },
    { label: 'Total PL2', value: moneyRound(t?.total_pl2), hint: 'Quarter plan' },
    { label: 'PL2 per sale', value: t?.total_sales ? money((t.total_pl2 ?? 0) / t.total_sales) : '—', hint: 'Total PL2 ÷ total sales' },
    ...(plan.value?.months ?? []).map((m, i) => ({ label: `PL2 · ${m}`, value: moneyRound(t?.pl2[i]), hint: `${num(t?.sales[i])} sales` })),
  ]
})

/** Footer = the plan's own total row (as written in the sheet). Leaf columns: 5 fixed, then each month group. */
function footer(): string[] {
  const t = plan.value?.total
  if (!t) return []
  return ['Total', '', num(t.total_sales), moneyRound(t.total_pl2), pct(t.share),
    ...t.sales.map(num), ...t.sales_per_day.map((v) => pcs(v)), ...t.pl2.map(moneyRound)]
}
</script>

<template>
  <PageHeader :subtitle="subtitle">
    <template #actions>
      <el-button v-if="plan" tag="a" :href="plan.sheet.url" target="_blank" rel="noopener" :icon="Link">Open in Lark</el-button>
      <el-button :icon="Refresh" :loading="syncing || loading" :disabled="!plan" @click="sync">Sync</el-button>
    </template>
  </PageHeader>

  <el-alert v-if="error" type="warning" :title="error" :closable="false" show-icon class="!mb-4">
    <RouterLink v-if="auth.isAdmin.value" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
  </el-alert>

  <template v-if="plan">
    <el-alert v-if="plan.sheet.last_error" type="error" :title="plan.sheet.last_error" :closable="false" show-icon class="!mb-4"
              description="The plan below is from the last successful sync." />

    <div class="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <div v-for="k in kpis" :key="k.label" class="kpi">
        <div class="kpi__label">{{ k.label }}</div>
        <div class="kpi__value">{{ k.value }}</div>
        <div class="mt-1 text-xs text-muted">{{ k.hint }}</div>
      </div>
    </div>

    <div class="section-card">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 class="card-title !mb-0">Plan by product</h3>
        <div class="flex items-center gap-3">
          <el-segmented v-if="showChart" v-model="metric" :options="[{ label: 'PL2', value: 'pl2' }, { label: 'Sales', value: 'sales' }]" size="small" class="segmented-tabs" />
          <el-switch v-model="showChart" active-text="Chart" />
        </div>
      </div>

      <PlanChart v-if="showChart" :products="plan.products" :months="plan.months" :metric="metric" class="mb-3" />

      <el-table v-loading="loading" :data="plan.products" border show-summary :summary-method="footer" empty-text="No product in the plan" class="w-full">
        <el-table-column label="Product" prop="product" fixed min-width="170">
          <template #default="{ row }"><span class="font-medium text-slate-900">{{ row.product }}</span></template>
        </el-table-column>
        <el-table-column label="PL2/item" prop="pl2_per_item" width="95" align="right"><template #default="{ row }"><span class="num">{{ money(row.pl2_per_item) }}</span></template></el-table-column>
        <el-table-column label="Total sales" prop="total_sales" width="115" align="right" sortable><template #default="{ row }"><span class="num">{{ num(row.total_sales) }}</span></template></el-table-column>
        <el-table-column label="Total PL2" prop="total_pl2" width="120" align="right" sortable>
          <template #default="{ row }"><span class="num font-semibold text-slate-900">{{ moneyRound(row.total_pl2) }}</span></template>
        </el-table-column>
        <el-table-column label="Share" prop="share" width="90" align="right" sortable><template #default="{ row }"><span class="num">{{ pct(row.share) }}</span></template></el-table-column>
        <el-table-column label="Sales / month" align="center">
          <el-table-column v-for="(m, i) in plan.months" :key="`sales-${m}`" :label="m" width="95" align="right">
            <template #default="{ row }"><span class="num">{{ num(row.sales[i]) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="Sales / day" align="center">
          <el-table-column v-for="(m, i) in plan.months" :key="`day-${m}`" :label="m" width="95" align="right">
            <template #default="{ row }"><span class="num">{{ pcs(row.sales_per_day[i]) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="PL2 / month" align="center">
          <el-table-column v-for="(m, i) in plan.months" :key="`pl2-${m}`" :label="m" width="105" align="right">
            <template #default="{ row }"><span class="num">{{ moneyRound(row.pl2[i]) }}</span></template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <div class="mt-2 text-xs text-muted">
        Read from the last sync of the sheet ({{ plan.products.length }} of up to {{ plan.max_products }} products). Press Sync after the team edits the plan in Lark.
      </div>
    </div>
  </template>
</template>
