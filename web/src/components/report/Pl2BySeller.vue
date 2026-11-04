<script setup lang="ts">
import { computed, onMounted, ref, watch, type VNode } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ShareBarChart from './ShareBarChart.vue'
import { auth } from '../../lib/auth'
import { dateTime, money, num, pct } from '../../lib/format'
import { cfColor, cfTotal, gapColor, KT_COLOR, perDay, perDayValue, rangeDays, signedMoney } from '../../lib/plan'
import { downloadCsv, fetchPl2Sellers } from '../../lib/report'
import type { Pl2SellerLine, Pl2Sellers } from '../../lib/types'

// Etsy › Report: PL2 of each seller, estimated from sales (KT) next to their PL2 plan to date and finance's "Profit tính KPI" (CF)
const props = defineProps<{ params: Record<string, string> }>()
const data = ref<Pl2Sellers | null>(null)
const loading = ref(false)
const error = ref('')
const showChart = ref(true)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchPl2Sellers(props.params)
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

const days = computed(() => rangeDays(props.params.date_from, props.params.date_to)) // Avg sales/day
const hasKt = computed(() => !!data.value && !data.value.kt.error)
const hasPlan = computed(() => !!data.value && !data.value.plan.error && data.value.total.plan != null)
const hasCf = computed(() => !!data.value && !data.value.cf.error)
const rows = computed(() => data.value?.sellers ?? [])
const total = computed(() => data.value?.total)
const rowClass = ({ row }: { row: Pl2SellerLine }) => (row.in_plan ? '' : 'row-child')

// share charts: each seller's part of All sellers' PL2, leaving out those at 0
function shares(field: 'kt' | 'cf') {
  return rows.value.filter((l) => Math.round((l[field] ?? 0) * 100)).map((l) => ({ name: l.seller, value: l[field] as number }))
}
const ktShares = computed(() => (hasKt.value ? shares('kt') : []))
const cfShares = computed(() => (hasCf.value ? shares('cf') : []))
const ktColor = () => KT_COLOR

// the plan counts the report's days pro rata; CF is booked per month, so the months the range touches count whole
const touched = (months: string[] | undefined) => {
  const [from, to] = [props.params.date_from, props.params.date_to].map((d) => d?.slice(0, 7))
  return (months ?? []).filter((m) => {
    const [mm, yyyy] = m.split('-')
    return `${yyyy}-${mm}` >= from && `${yyyy}-${mm}` <= to
  })
}
const source = computed(() => {
  const d = data.value
  if (!d) return ''
  const parts: string[] = []
  if (d.plan.sheet) parts.push(`Plan: ${d.plan.sheet.name.trim()} · ${d.plan.sheet.tab_title.trim()} · synced ${dateTime(d.plan.sheet.last_synced_at)}`)
  if (d.cf.sheets?.length) {
    const latest = d.cf.sheets.map((s) => s.last_synced_at).filter(Boolean).sort().at(-1) ?? null
    parts.push(`CF: Profit tính KPI ${touched(d.cf.months).join(', ') || '—'} · ${d.cf.sheets.length} seller P&L tab(s) · synced ${dateTime(latest)}`)
  }
  return parts.join('   ')
})
const notes = computed(() => {
  const d = data.value
  if (!d) return []
  const out: string[] = []
  if (d.plan.missing?.length) out.push(`The seller plan sheet has no plan for ${d.plan.missing.join(', ')}`)
  if (d.cf.missing?.length) out.push(`The seller CF sheets have no PL2 for ${d.cf.missing.join(', ')}`)
  return out
})
const kpis = computed(() => {
  const t = total.value
  const d = data.value
  const withPlan = hasPlan.value
  return [
    { label: 'Sellers', value: d ? num(d.sellers.length) : '—', hint: d?.sellers.some((s) => !s.in_plan) ? 'Plan sellers, then others with a PL2' : 'Sellers of the plan sheet' },
    ...(withPlan ? [{ label: 'PL2 plan to date', value: money(t?.plan), hint: 'Seller plan sheet, pro rata of the days' }] : []),
    ...(hasKt.value ? [{ label: 'PL2 KT (est.)', value: money(t?.kt), hint: 'Quantity × the plan\'s PL2/item' }] : []),
    ...(hasKt.value && withPlan ? [{ label: 'KT gap', value: signedMoney(t?.kt_gap) || '—', color: gapColor(t?.kt_gap), hint: `PL2 KT − plan · ${pct(t?.kt_pct, 1)} of plan` }] : []),
    ...(hasCf.value ? [{ label: 'PL2 CF (actual)', value: money(t?.cf), color: cfColor(t?.cf), hint: `Profit tính KPI, ${touched(data.value?.cf.months).join(', ') || 'months of the range'}` }] : []),
    ...(hasCf.value && withPlan ? [{ label: 'CF gap', value: signedMoney(t?.cf_gap) || '—', color: gapColor(t?.cf_gap), hint: `PL2 CF − plan · ${pct(t?.cf_pct, 1)} of plan` }] : []),
  ]
})

function footer(): (string | VNode)[] {
  const t = total.value
  if (!t) return []
  return ['All sellers', num(t.quantity), perDay(t.quantity, days.value),
    ...(hasPlan.value ? [money(t.plan)] : []),
    ...(hasKt.value ? [money(t.kt)] : []),
    ...(hasKt.value && hasPlan.value ? [signedMoney(t.kt_gap), pct(t.kt_pct, 1)] : []),
    ...(hasCf.value ? [cfTotal(t.cf, money(t.cf))] : []),
    ...(hasCf.value && hasPlan.value ? [signedMoney(t.cf_gap), pct(t.cf_pct, 1)] : []),
    ...(hasKt.value && hasCf.value ? [signedMoney(t.cf_minus_kt)] : [])]
}

function exportCsv() {
  if (!data.value) return
  const header = ['Seller', 'Trackingis seller', 'In plan', 'Quantity', 'Avg sales/day', 'PL2 plan to date', 'PL2 KT (est.)', 'KT gap',
    'KT % of plan', 'PL2 CF (actual)', 'CF gap', 'CF % of plan', 'CF − KT']
  const body = data.value.sellers.map((r) => [r.seller, r.sellers.join(' + '), r.in_plan ? 'yes' : 'no', r.quantity, perDayValue(r.quantity, days.value),
    r.plan ?? '', r.kt ?? '', r.kt_gap ?? '', r.kt_pct ?? '', r.cf ?? '', r.cf_gap ?? '', r.cf_pct ?? '', r.cf_minus_kt ?? ''])
  downloadCsv(`pl2-by-seller-${props.params.date_from}_${props.params.date_to}.csv`, header, body)
  ElMessage.success(`Exported ${body.length} sellers`)
}
</script>

<template>
  <div class="section-card">
    <div class="mb-1 flex flex-wrap items-center justify-between gap-3">
      <h3 class="card-title !mb-0">PL2 by seller: KT vs plan{{ hasCf ? ' vs CF' : '' }}</h3>
      <div class="flex items-center gap-3">
        <el-switch v-model="showChart" active-text="Chart" />
        <el-button size="small" type="success" plain :icon="Download" :disabled="!rows.length" @click="exportCsv">Export</el-button>
      </div>
    </div>
    <div v-if="source" class="mb-3 text-xs text-muted">{{ source }}</div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!my-3" />
    <template v-else-if="data">
      <el-alert v-if="data.kt.error" type="info" :closable="false" show-icon :title="data.kt.error" class="!my-3" />
      <el-alert v-if="data.plan.error && !auth.ownSalesOnly.value" type="info" :closable="false" show-icon :title="data.plan.error" class="!my-3">
        <RouterLink v-if="auth.isAdmin.value && data.plan.error.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
      </el-alert>
      <el-alert v-if="data.cf.error && data.cf.error !== data.plan.error && !auth.ownSalesOnly.value" type="info" :closable="false" show-icon
                :title="data.cf.error" class="!my-3">
        <RouterLink v-if="auth.isAdmin.value && data.cf.error.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
      </el-alert>
      <el-alert v-for="n in notes" :key="n" type="warning" :closable="false" show-icon :title="n" class="!my-3" />
    </template>

    <div v-loading="loading" class="mb-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <div v-for="k in kpis" :key="k.label" class="kpi">
        <div class="kpi__label">{{ k.label }}</div>
        <div class="kpi__value" :style="k.color ? { color: k.color } : undefined">{{ k.value }}</div>
        <div v-if="k.hint" class="mt-1 text-xs text-muted">{{ k.hint }}</div>
      </div>
    </div>

    <div v-if="showChart && (ktShares.length || cfShares.length)" class="mb-3 grid gap-3 lg:grid-cols-2">
      <ShareBarChart v-if="ktShares.length" title="PL2 KT share by seller" value-label="PL2 KT (est.)" :items="ktShares"
                     :total="total?.kt" :color="ktColor" />
      <ShareBarChart v-if="cfShares.length" title="PL2 CF share by seller" value-label="PL2 CF (actual)" :items="cfShares"
                     :total="total?.cf" :color="cfColor" />
    </div>

    <el-table v-loading="loading" :data="rows" row-key="seller" :row-class-name="rowClass" show-summary :summary-method="footer"
              empty-text="No seller with a PL2 for these filters" max-height="640" class="w-full">
      <el-table-column label="Seller" min-width="190" fixed>
        <template #default="{ row }">
          <span>{{ row.seller }}</span>
          <span v-if="row.sellers.length && row.sellers.join(' + ') !== row.seller" class="ml-1 text-xs text-muted">{{ row.sellers.join(' + ') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="Quantity" prop="quantity" width="100" align="right" sortable>
        <template #default="{ row }"><span class="num">{{ num(row.quantity) }}</span></template>
      </el-table-column>
      <el-table-column label="Avg sales/day" prop="quantity" width="95" align="right">
        <template #default="{ row }"><span class="num">{{ perDay(row.quantity, days) }}</span></template>
      </el-table-column>
      <el-table-column v-if="hasPlan" label="PL2 plan to date" prop="plan" min-width="125" align="right" sortable>
        <template #default="{ row }"><span class="num text-muted" title="The seller plan sheet's PL2, pro rata of the days">{{ row.plan == null ? '' : money(row.plan) }}</span></template>
      </el-table-column>
      <el-table-column v-if="hasKt" label="PL2 KT (est.)" prop="kt" min-width="120" align="right" sortable>
        <template #default="{ row }"><span class="num font-semibold">{{ row.kt == null ? '' : money(row.kt) }}</span></template>
      </el-table-column>
      <template v-if="hasKt && hasPlan">
        <el-table-column label="KT gap" prop="kt_gap" min-width="115" align="right" sortable>
          <template #default="{ row }">
            <span class="num font-semibold" :style="{ color: gapColor(row.kt_gap) }" title="PL2 KT − plan to date">{{ signedMoney(row.kt_gap) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="KT %" prop="kt_pct" width="80" align="right" sortable>
          <template #default="{ row }"><span class="num text-muted" title="PL2 KT / plan to date">{{ row.kt_pct == null ? '' : pct(row.kt_pct, 1) }}</span></template>
        </el-table-column>
      </template>
      <el-table-column v-if="hasCf" label="PL2 CF (actual)" prop="cf" min-width="125" align="right" sortable class-name="cf-cell">
        <template #default="{ row }"><span class="num" :style="{ color: cfColor(row.cf) }">{{ row.cf == null ? '' : money(row.cf) }}</span></template>
      </el-table-column>
      <template v-if="hasCf && hasPlan">
        <el-table-column label="CF gap" prop="cf_gap" min-width="115" align="right" sortable>
          <template #default="{ row }">
            <span class="num font-semibold" :style="{ color: gapColor(row.cf_gap) }" title="PL2 CF − plan to date">{{ signedMoney(row.cf_gap) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="CF %" prop="cf_pct" width="80" align="right" sortable>
          <template #default="{ row }"><span class="num text-muted" title="PL2 CF / plan to date">{{ row.cf_pct == null ? '' : pct(row.cf_pct, 1) }}</span></template>
        </el-table-column>
      </template>
      <el-table-column v-if="hasKt && hasCf" label="CF − KT" prop="cf_minus_kt" min-width="115" align="right" sortable>
        <template #default="{ row }">
          <span class="num font-semibold" :style="{ color: gapColor(row.cf_minus_kt) }"
                title="PL2 CF − PL2 KT: what finance books against the estimate">{{ signedMoney(row.cf_minus_kt) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="mt-2 text-xs text-muted">
      One row per seller of the seller plan sheet, in its order; sellers outside it are listed after them when they have a PL2 (KT or
      CF not 0), with a plan of $0, so their whole PL2 is their gap. PL2 KT = the seller's quantity of each plan product × that
      product's PL2/item, for the report's days (pieces added by hand, Felt, are not tied to a seller). PL2 plan to date = the
      seller plan sheet's PL2 of each month pro rata of the days. PL2 CF = finance's "Profit tính KPI" of the seller (the
      "1.2 P&amp;L Seller" tabs), booked per month: the range counts the whole months it touches. KT gap = KT − plan, CF gap = CF − plan,
      KT % and CF % = KT or CF as a share of the plan, CF − KT = PL2 CF − PL2 KT. The sheets name sellers by first name (Linh), trackingis by
      account (Linh PT.ETS): they are matched on the first name. Plan and CF are per seller across all stores, so a store, team, designer
      or keyword filter leaves them out.
    </div>
  </div>
</template>
