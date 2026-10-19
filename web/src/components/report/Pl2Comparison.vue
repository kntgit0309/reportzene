<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { auth } from '../../lib/auth'
import { dateTime, money, pct } from '../../lib/format'
import { bar, barColor, gapColor } from '../../lib/plan'
import { fetchPl2 } from '../../lib/report'
import type { Pl2Month, Pl2Report } from '../../lib/types'

type Row = Partial<Pl2Month> & { key: string; label: string; children?: Row[] }

// Etsy › Report: finance's monthly PL2 (PL2 theo CF) next to the PL2 estimated from sales (PL2 theo KT), for the report's filters
const signedMoney = (v: number | null | undefined) => (v == null ? '' : (v > 0 ? '+' : '') + money(v))
const props = defineProps<{ params: Record<string, string> }>()
const data = ref<Pl2Report | null>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchPl2(props.params)
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

const cf = computed(() => data.value?.cf)
const hasCf = computed(() => !!cf.value && !cf.value.error)
const rows = computed<Row[]>(() => (data.value?.months ?? []).map((m) => ({
  ...m, key: m.month, label: m.days === m.month_days ? m.month : `${m.month} (${m.days}/${m.month_days} days)`,
  children: m.teams?.map((t) => ({ ...t, key: `${m.month}/${t.team}`, label: t.team })),
})))
const total = computed(() => data.value?.total)
const source = computed(() => {
  const c = cf.value
  return c?.sheet ? `${c.sheet.name.trim()} · ${c.sheet.tab_title.trim()} · ${c.scope} · synced ${dateTime(c.sheet.last_synced_at)}` : ''
})
const kpis = computed(() => {
  const t = total.value
  const cfCards = hasCf.value ? [
    { label: 'PL2 plan (CF)', value: money(t?.plan), hint: `Plan to date ${money(t?.plan_to_date)}` },
    { label: 'PL2 actual (CF)', value: money(t?.actual), hint: 'As finance books it, month so far' },
    { label: 'Gap (CF)', value: signedMoney(t?.gap) || '—', color: gapColor(t?.gap ?? undefined), hint: 'Actual (CF) − plan to date' },
    { label: '% of plan (CF)', value: pct(t?.achieved, 0), achieved: t?.achieved, color: barColor(t?.achieved) }, // of plan to date
  ] : []
  return [
    ...cfCards,
    { label: 'PL2 KT (est.)', value: money(t?.kt), hint: 'Quantity × the plan\'s PL2/item, same days' },
    ...(hasCf.value ? [{ label: 'KT − CF', value: signedMoney(t?.kt_minus_cf) || '—', hint: 'PL2 KT − PL2 actual (CF)' }] : []),
  ]
})
const rowClass = ({ row }: { row: Row }) => (row.children ? 'row-parent' : 'row-child')
function footer(): string[] {
  const t = total.value
  if (!t) return []
  const cfCells = hasCf.value ? [money(t.plan), money(t.plan_to_date), money(t.actual), signedMoney(t.gap), pct(t.achieved, 0)] : []
  return ['All months', ...cfCells, money(t.kt), ...(hasCf.value ? [signedMoney(t.kt_minus_cf)] : [])]
}
</script>

<template>
  <div class="section-card">
    <h3 class="card-title !mb-1">PL2: KT vs CF</h3>
    <div v-if="hasCf" class="mb-3 text-xs text-muted">{{ source }}</div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!my-3" />
    <el-alert v-else-if="data && !hasCf" type="info" :closable="false" show-icon :title="cf?.error" class="!my-3">
      <RouterLink v-if="auth.isAdmin.value && cf?.error?.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
    </el-alert>

    <div v-loading="loading" class="mb-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <div v-for="k in kpis" :key="k.label" class="kpi">
        <div class="kpi__label">{{ k.label }}</div>
        <div class="kpi__value" :style="k.color ? { color: k.color } : undefined">{{ k.value }}</div>
        <el-progress v-if="'achieved' in k" :percentage="bar(k.achieved)" :color="barColor(k.achieved)" :show-text="false" :stroke-width="6" class="mt-2" />
        <div v-else-if="k.hint" class="mt-1 text-xs text-muted">{{ k.hint }}</div>
      </div>
    </div>

    <el-table v-loading="loading" :data="rows" row-key="key" :tree-props="{ children: 'children' }" :row-class-name="rowClass"
              show-summary :summary-method="footer" empty-text="No month in this range" class="w-full">
      <el-table-column label="Month / Team" min-width="190" class-name="tree-cell">
        <template #default="{ row }">{{ row.label }}</template>
      </el-table-column>
      <template v-if="hasCf">
        <el-table-column label="Plan (CF)" prop="plan" min-width="120" align="right">
          <template #default="{ row }"><span class="num">{{ row.plan == null ? '' : money(row.plan) }}</span></template>
        </el-table-column>
        <el-table-column label="Plan to date" prop="plan_to_date" min-width="120" align="right">
          <template #default="{ row }"><span class="num text-muted">{{ row.plan_to_date == null ? '' : money(row.plan_to_date) }}</span></template>
        </el-table-column>
        <el-table-column label="Actual (CF)" prop="actual" min-width="120" align="right">
          <template #default="{ row }"><span class="num font-semibold text-slate-900">{{ row.actual == null ? '' : money(row.actual) }}</span></template>
        </el-table-column>
        <el-table-column label="Gap (CF)" prop="gap" min-width="120" align="right">
          <template #default="{ row }">
            <span class="num font-semibold" :style="{ color: gapColor(row.gap ?? undefined) }" title="Actual (CF) − plan to date">{{ signedMoney(row.gap) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="% of plan (CF)" prop="achieved" width="150">
          <template #default="{ row }">
            <div v-if="row.plan" class="flex items-center gap-2">
              <el-progress :percentage="bar(row.achieved)" :color="barColor(row.achieved)" :show-text="false" :stroke-width="6" class="flex-1" />
              <span class="num w-11 text-right text-xs font-semibold" :style="{ color: barColor(row.achieved) }">{{ pct(row.achieved, 0) }}</span>
            </div>
          </template>
        </el-table-column>
      </template>
      <el-table-column label="PL2 KT (est.)" prop="kt" min-width="120" align="right">
        <template #default="{ row }"><span class="num font-semibold">{{ row.kt == null ? '' : money(row.kt) }}</span></template>
      </el-table-column>
      <el-table-column v-if="hasCf" label="KT − CF" prop="kt_minus_cf" min-width="120" align="right">
        <template #default="{ row }">
          <span class="num font-semibold" title="PL2 KT − PL2 actual (CF): how far the estimate is from what finance books">
            {{ signedMoney(row.kt_minus_cf) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
    <div class="mt-2 text-xs text-muted">
      PL2 theo CF: finance's monthly PL2 plan and actual (the running month so far), for B.U ZenE (opens onto each team) or
      the teams filtered. PL2 theo KT: the estimate of Sales by product vs plan below (quantity × the plan's PL2/item) for the
      report's days of each month.
      Plan to date counts the CF plan pro rata of those days; Gap (CF) = Actual (CF) − Plan to date and % of plan = Actual / Plan
      to date. KT − CF = PL2 KT − PL2 actual (CF).
    </div>
  </div>
</template>
