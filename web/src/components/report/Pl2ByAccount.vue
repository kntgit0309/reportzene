<script setup lang="ts">
import { computed, onMounted, ref, watch, type VNode } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ShareBarChart from './ShareBarChart.vue'
import { auth } from '../../lib/auth'
import { dateTime, money, num, pct } from '../../lib/format'
import { cfColor, cfTotal, gapColor, KT_COLOR, perDay, perDayValue, rangeDays } from '../../lib/plan'
import { downloadCsv, fetchPl2Accounts } from '../../lib/report'
import type { Pl2AccountLine, Pl2Accounts } from '../../lib/types'

type Row = Pl2AccountLine & { key: string; count?: number; children?: Row[] }

// Etsy › Report: PL2 of each account of the plans, estimated from sales (KT) next to finance's PROFIT THỰC ĐẠT (CF), and the
// account's PL2 plan to date on each basis (KH theo Acc: KH theo KT, KH theo CF) with the gap
const signedMoney = (v: number | null | undefined) => (v == null ? '' : (v > 0 ? '+' : '') + money(v))
const props = defineProps<{ params: Record<string, string> }>()
const data = ref<Pl2Accounts | null>(null)
const loading = ref(false)
const error = ref('')
const showChart = ref(true)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchPl2Accounts(props.params)
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
const cf = computed(() => data.value?.cf)
const hasCf = computed(() => !!cf.value && !cf.value.error)
const hasKt = computed(() => !!data.value && !data.value.kt.error)
const hasKhPlan = computed(() => (data.value?.accounts ?? []).some((a) => a.plan != null)) // KH avg/day
const khPl2 = computed(() => data.value?.kh_pl2)
const hasKtPlan = computed(() => hasKt.value && !khPl2.value?.error && data.value?.total.kt_plan != null) // KH theo KT
const hasCfPlan = computed(() => hasCf.value && !khPl2.value?.error && data.value?.total.cf_plan != null) // KH theo CF
const rows = computed<Row[]>(() => {
  const d = data.value
  if (!d) return []
  const others: Row[] = d.others.count
    ? [{ ...d.others, key: '_others', children: d.others.children.map((c) => ({ ...c, key: `_others/${c.shop}` })) }]
    : []
  return [...d.accounts.map((a) => ({ ...a, key: a.shop })), ...others]
})
const total = computed(() => data.value?.total)
// share charts: each account of the plans and Other accounts as one bar, leaving out those at 0
function shares(field: 'kt' | 'cf') {
  const d = data.value
  if (!d) return []
  const lines = [...d.accounts, ...(d.others.count ? [{ ...d.others, shop: `Other accounts (${d.others.count})` }] : [])]
  return lines.filter((l) => Math.round((l[field] ?? 0) * 100)).map((l) => ({ name: l.shop, value: l[field] as number }))
}
const ktShares = computed(() => (hasKt.value ? shares('kt') : []))
const cfShares = computed(() => (hasCf.value ? shares('cf') : []))
const ktColor = () => KT_COLOR
// CF is booked per month: the months the range touches count whole
const cfMonths = computed(() => {
  const [from, to] = [props.params.date_from, props.params.date_to].map((d) => d?.slice(0, 7))
  const shown = (cf.value?.months ?? []).filter((m) => {
    const [mm, yyyy] = m.split('-')
    const ym = `${yyyy}-${mm}`
    return ym >= from && ym <= to
  })
  return shown.join(', ')
})
const source = computed(() => {
  const c = cf.value
  const k = khPl2.value
  const parts: string[] = []
  if (c?.sheet) {
    const names = c.list ? ` · names from ${c.list.name.trim()}` : ''
    parts.push(`${c.sheet.name.trim()} · ${c.sheet.tab_title.trim()} · PROFIT THỰC ĐẠT ${cfMonths.value || '—'}${names} · synced ${dateTime(c.sheet.last_synced_at)}`)
  }
  if (k?.sheet && !k.error) parts.push(`KH: ${k.sheet.name.trim()} · ${k.sheet.tab_title.trim()} · synced ${dateTime(k.sheet.last_synced_at)}`)
  return parts.join('   ')
})
// the plan alert says why there is no KH theo KT / CF; filters that cut across stores already got CF's note
const planAlert = computed(() => {
  const e = khPl2.value?.error
  return e && e !== cf.value?.error && !auth.ownSalesOnly.value ? e : ''
})
const planMissing = computed(() => (khPl2.value?.missing?.length ? `The account PL2 plan sheet has no plan for ${khPl2.value.missing.join(', ')}` : ''))
const title = computed(() => {
  if (!hasCf.value && !hasKtPlan.value && !hasCfPlan.value) return 'Sales and PL2 KT by account'
  return `PL2 by account: KT${hasKtPlan.value || hasCfPlan.value ? ' vs KH' : ''}${hasCf.value ? ' vs CF' : ''}`
})
const kpis = computed(() => {
  const t = total.value
  const d = data.value
  return [
    { label: 'Accounts in KH', value: d ? num(d.accounts.length) : '—', hint: d?.others.count ? `+ ${d.others.count} other accounts with a PL2` : 'Stores of the KH plan sheets' },
    ...(hasKtPlan.value ? [{ label: 'KH PL2 theo KT', value: money(t?.kt_plan), hint: 'Plan to date, pro rata of the days' }] : []),
    ...(hasKt.value ? [{ label: 'PL2 KT (est.)', value: money(t?.kt), hint: 'Quantity × the plan\'s PL2/item' }] : []),
    ...(hasKtPlan.value ? [{ label: 'KT gap', value: signedMoney(t?.kt_gap) || '—', color: gapColor(t?.kt_gap), hint: `PL2 KT − KH theo KT · ${pct(t?.kt_pct, 1)} of plan` }] : []),
    ...(hasCfPlan.value ? [{ label: 'KH PL2 theo CF', value: money(t?.cf_plan), hint: 'Plan to date, pro rata of the days' }] : []),
    ...(hasCf.value ? [
      { label: 'PL2 CF (actual)', value: money(t?.cf), color: cfColor(t?.cf), hint: `PROFIT THỰC ĐẠT, ${cfMonths.value || 'months of the range'}` },
    ] : []),
    ...(hasCfPlan.value ? [{ label: 'CF gap', value: signedMoney(t?.cf_gap) || '—', color: gapColor(t?.cf_gap), hint: `PL2 CF − KH theo CF · ${pct(t?.cf_pct, 1)} of plan` }] : []),
    ...(hasKt.value && hasCf.value ? [{ label: 'CF − KT', value: signedMoney(t?.cf_minus_kt) || '—', color: gapColor(t?.cf_minus_kt), hint: 'PL2 CF − PL2 KT' }] : []),
  ]
})
const rowClass = ({ row }: { row: Row }) => (row.children ? 'row-parent' : row.key.startsWith('_others/') ? 'row-child' : '')

function footer(): (string | VNode)[] {
  const t = total.value
  if (!t) return []
  return ['All accounts', '', num(t.quantity), perDay(t.quantity, days.value), ...(hasKhPlan.value ? [perDay(t.plan, days.value)] : []),
    ...(hasKtPlan.value ? [money(t.kt_plan)] : []), ...(hasKt.value ? [money(t.kt)] : []),
    ...(hasKtPlan.value ? [signedMoney(t.kt_gap), pct(t.kt_pct, 1)] : []),
    ...(hasCfPlan.value ? [money(t.cf_plan)] : []), ...(hasCf.value ? [cfTotal(t.cf, money(t.cf))] : []),
    ...(hasCfPlan.value ? [signedMoney(t.cf_gap), pct(t.cf_pct, 1)] : []),
    ...(hasKt.value && hasCf.value ? [signedMoney(t.cf_minus_kt)] : [])]
}

function exportCsv() {
  const d = data.value
  if (!d) return
  const header = ['Account', 'Team', 'In KH', 'Quantity', 'Avg sales/day', 'KH avg/day', 'KH PL2 theo KT', 'PL2 KT (est.)', 'KT gap',
    'KT % of plan', 'KH PL2 theo CF', 'PL2 CF (actual)', 'CF gap', 'CF % of plan', 'CF − KT']
  const line = (r: Pl2AccountLine, inKh: string) => [r.shop, r.team ?? '', inKh, r.quantity, perDayValue(r.quantity, days.value),
    perDayValue(r.plan, days.value), r.kt_plan ?? '', r.kt ?? '', r.kt_gap ?? '', r.kt_pct ?? '',
    r.cf_plan ?? '', r.cf ?? '', r.cf_gap ?? '', r.cf_pct ?? '', r.cf_minus_kt ?? '']
  const body = [...d.accounts.map((a) => line(a, 'yes')), ...d.others.children.map((c) => line(c, 'no'))]
  downloadCsv(`pl2-by-account-${props.params.date_from}_${props.params.date_to}.csv`, header, body)
  ElMessage.success(`Exported ${body.length} accounts`)
}
</script>

<template>
  <div class="section-card">
    <div class="mb-1 flex flex-wrap items-center justify-between gap-3">
      <h3 class="card-title !mb-0">{{ title }}</h3>
      <div class="flex items-center gap-3">
        <el-switch v-model="showChart" active-text="Chart" />
        <el-button size="small" type="success" plain :icon="Download" :disabled="!rows.length" @click="exportCsv">Export</el-button>
      </div>
    </div>
    <div v-if="source" class="mb-3 text-xs text-muted">{{ source }}</div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!my-3" />
    <template v-else-if="data">
      <el-alert v-if="data.kt.error" type="info" :closable="false" show-icon :title="data.kt.error" class="!my-3" />
      <el-alert v-if="!hasCf && !auth.ownSalesOnly.value" type="info" :closable="false" show-icon :title="cf?.error" class="!my-3">
        <RouterLink v-if="auth.isAdmin.value && cf?.error?.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
      </el-alert>
      <el-alert v-if="planAlert" type="info" :closable="false" show-icon :title="planAlert" class="!my-3">
        <RouterLink v-if="auth.isAdmin.value && planAlert.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
      </el-alert>
      <el-alert v-if="planMissing && (hasKtPlan || hasCfPlan)" type="warning" :closable="false" show-icon :title="planMissing" class="!my-3" />
      <el-alert v-for="w in cf?.warnings ?? []" :key="w" type="warning" :closable="false" show-icon :title="w" class="!my-3" />
    </template>

    <div v-loading="loading" class="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
      <div v-for="k in kpis" :key="k.label" class="kpi">
        <div class="kpi__label">{{ k.label }}</div>
        <div class="kpi__value" :style="k.color ? { color: k.color } : undefined">{{ k.value }}</div>
        <div v-if="k.hint" class="mt-1 text-xs text-muted">{{ k.hint }}</div>
      </div>
    </div>

    <div v-if="showChart && (ktShares.length || cfShares.length)" class="mb-3 grid gap-3 lg:grid-cols-2">
      <ShareBarChart v-if="ktShares.length" title="PL2 KT share by account" value-label="PL2 KT (est.)" :items="ktShares"
                     :total="total?.kt" :color="ktColor" />
      <ShareBarChart v-if="cfShares.length" title="PL2 CF share by account" value-label="PL2 CF (actual)" :items="cfShares"
                     :total="total?.cf" :color="cfColor" />
    </div>

    <el-table v-loading="loading" :data="rows" row-key="key" :tree-props="{ children: 'children' }" :row-class-name="rowClass"
              show-summary :summary-method="footer" empty-text="No account in the KH sheets for these filters" max-height="640" class="w-full">
      <el-table-column label="Account" min-width="210" class-name="tree-cell" fixed>
        <template #default="{ row }">
          <span v-if="row.children">{{ row.shop }} <span class="text-xs text-muted">({{ row.count }})</span></span>
          <span v-else>{{ row.shop }}</span>
        </template>
      </el-table-column>
      <el-table-column label="Team" prop="team" width="90">
        <template #default="{ row }"><span class="text-muted">{{ row.team ?? '' }}</span></template>
      </el-table-column>
      <el-table-column label="Quantity" prop="quantity" width="100" align="right" sortable>
        <template #default="{ row }"><span class="num">{{ num(row.quantity) }}</span></template>
      </el-table-column>
      <el-table-column label="Avg sales/day" prop="quantity" width="95" align="right">
        <template #default="{ row }"><span class="num">{{ perDay(row.quantity, days) }}</span></template>
      </el-table-column>
      <el-table-column v-if="hasKhPlan" label="KH avg/day" prop="plan" width="85" align="right">
        <template #default="{ row }"><span class="num text-muted" title="KH plan to date ÷ the days">{{ row.plan == null ? '' : perDay(row.plan, days) }}</span></template>
      </el-table-column>
      <el-table-column v-if="hasKtPlan" label="KH PL2 theo KT" prop="kt_plan" min-width="125" align="right" sortable>
        <template #default="{ row }"><span class="num text-muted" title="KH theo Acc: PL2 plan on the KT basis, pro rata of the days">{{ row.kt_plan == null ? '' : money(row.kt_plan) }}</span></template>
      </el-table-column>
      <el-table-column v-if="hasKt" label="PL2 KT (est.)" prop="kt" min-width="120" align="right" sortable>
        <template #default="{ row }"><span class="num font-semibold">{{ row.kt == null ? '' : money(row.kt) }}</span></template>
      </el-table-column>
      <template v-if="hasKtPlan">
        <el-table-column label="KT gap" prop="kt_gap" min-width="115" align="right" sortable>
          <template #default="{ row }">
            <span class="num font-semibold" :style="{ color: gapColor(row.kt_gap) }" title="PL2 KT − KH theo KT">{{ signedMoney(row.kt_gap) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="KT %" prop="kt_pct" width="80" align="right" sortable>
          <template #default="{ row }"><span class="num text-muted" title="PL2 KT / KH theo KT">{{ row.kt_pct == null ? '' : pct(row.kt_pct, 1) }}</span></template>
        </el-table-column>
      </template>
      <el-table-column v-if="hasCfPlan" label="KH PL2 theo CF" prop="cf_plan" min-width="125" align="right" sortable>
        <template #default="{ row }"><span class="num text-muted" title="KH theo Acc: PL2 plan on the CF basis, pro rata of the days">{{ row.cf_plan == null ? '' : money(row.cf_plan) }}</span></template>
      </el-table-column>
      <el-table-column v-if="hasCf" label="PL2 CF (actual)" prop="cf" min-width="125" align="right" sortable class-name="cf-cell">
        <template #default="{ row }"><span class="num" :style="{ color: cfColor(row.cf) }">{{ row.cf == null ? '' : money(row.cf) }}</span></template>
      </el-table-column>
      <template v-if="hasCfPlan">
        <el-table-column label="CF gap" prop="cf_gap" min-width="115" align="right" sortable>
          <template #default="{ row }">
            <span class="num font-semibold" :style="{ color: gapColor(row.cf_gap) }" title="PL2 CF − KH theo CF">{{ signedMoney(row.cf_gap) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="CF %" prop="cf_pct" width="80" align="right" sortable>
          <template #default="{ row }"><span class="num text-muted" title="PL2 CF / KH theo CF">{{ row.cf_pct == null ? '' : pct(row.cf_pct, 1) }}</span></template>
        </el-table-column>
      </template>
      <el-table-column v-if="hasKt && hasCf" label="CF − KT" prop="cf_minus_kt" min-width="120" align="right" sortable>
        <template #default="{ row }">
          <span class="num font-semibold" :style="{ color: gapColor(row.cf_minus_kt) }"
                title="PL2 CF − PL2 KT: what finance books against the estimate">{{ signedMoney(row.cf_minus_kt) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="mt-2 text-xs text-muted">
      One row per account of the KH plan sheets (Ornament, Shirt, Blanket…), in their order; a suspended store counts as the one that
      takes over (Settings › Plan). Other accounts adds up the stores outside the plans that have a PL2 (KT or CF not 0); All accounts
      is the plans' accounts plus them. PL2 KT = the account's quantity of each plan product × that product's PL2/item, for the
      report's days (pieces added by hand, Felt, are not tied to an account). KH avg/day = the account's plan to date in
      the KH sheets that plan per store (Ornament, Shirt, Blanket, Quilted, Flag, Wooden Block, Badge Reel) ÷ the days. PL2 CF = finance's PROFIT THỰC ĐẠT of the account
      ("PL Account Etsy_Monthly"), booked per month: the range counts the whole months it touches. CF − KT = PL2 CF − PL2 KT.
      KH PL2 theo KT and KH PL2 theo CF = the account's PL2 plan in the KHKD tab "KH theo Acc" (the "PL2 theo KT" and "PL2 theo CF"
      blocks), each month pro rata of the report's days; KT gap = PL2 KT − KH theo KT, CF gap = PL2 CF − KH theo CF, KT % and CF % =
      the share of that plan. An account the tab does not list has a plan of $0, so its whole PL2 is its gap and the rows add up to
      All accounts; accounts of the tab that no KH store sheet lists are rows of their own. A seller filter scales the plan by the
      seller's share of the month; the other seller, designer and keyword filters leave it out.
      The share charts show each account's part of All accounts' PL2 (accounts at 0 left out); a negative CF is a negative
      share, so the other shares can add up to more than 100%.
    </div>
  </div>
</template>
