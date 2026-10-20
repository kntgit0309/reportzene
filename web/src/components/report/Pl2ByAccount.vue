<script setup lang="ts">
import { computed, onMounted, ref, watch, type VNode } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { auth } from '../../lib/auth'
import { dateTime, money, num } from '../../lib/format'
import { cfColor, cfTotal, gapColor, perDay, perDayValue, rangeDays } from '../../lib/plan'
import { downloadCsv, fetchPl2Accounts } from '../../lib/report'
import type { Pl2AccountLine, Pl2Accounts } from '../../lib/types'

type Row = Pl2AccountLine & { key: string; count?: number; children?: Row[] }

// Etsy › Report: PL2 of each account of the plans, estimated from sales (KT) next to finance's PROFIT THỰC ĐẠT (CF)
const signedMoney = (v: number | null | undefined) => (v == null ? '' : (v > 0 ? '+' : '') + money(v))
const props = defineProps<{ params: Record<string, string> }>()
const data = ref<Pl2Accounts | null>(null)
const loading = ref(false)
const error = ref('')

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
const rows = computed<Row[]>(() => {
  const d = data.value
  if (!d) return []
  const others: Row[] = d.others.count
    ? [{ ...d.others, key: '_others', children: d.others.children.map((c) => ({ ...c, key: `_others/${c.shop}` })) }]
    : []
  return [...d.accounts.map((a) => ({ ...a, key: a.shop })), ...others]
})
const total = computed(() => data.value?.total)
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
  if (!c?.sheet) return ''
  const names = c.list ? ` · names from ${c.list.name.trim()}` : ''
  return `${c.sheet.name.trim()} · ${c.sheet.tab_title.trim()} · PROFIT THỰC ĐẠT ${cfMonths.value || '—'}${names} · synced ${dateTime(c.sheet.last_synced_at)}`
})
const kpis = computed(() => {
  const t = total.value
  const d = data.value
  return [
    { label: 'Accounts in KH', value: d ? num(d.accounts.length) : '—', hint: d?.others.count ? `+ ${d.others.count} other accounts with a PL2` : 'Stores of the KH plan sheets' },
    ...(hasKt.value ? [{ label: 'PL2 KT (est.)', value: money(t?.kt), hint: 'Quantity × the plan\'s PL2/item' }] : []),
    ...(hasCf.value ? [
      { label: 'PL2 CF (actual)', value: money(t?.cf), color: cfColor(t?.cf), hint: `PROFIT THỰC ĐẠT, ${cfMonths.value || 'months of the range'}` },
    ] : []),
    ...(hasKt.value && hasCf.value ? [{ label: 'CF − KT', value: signedMoney(t?.cf_minus_kt) || '—', color: gapColor(t?.cf_minus_kt), hint: 'PL2 CF − PL2 KT' }] : []),
  ]
})
const rowClass = ({ row }: { row: Row }) => (row.children ? 'row-parent' : row.key.startsWith('_others/') ? 'row-child' : '')

function footer(): (string | VNode)[] {
  const t = total.value
  if (!t) return []
  return ['All accounts', '', num(t.quantity), perDay(t.quantity, days.value), ...(hasKt.value ? [money(t.kt)] : []),
    ...(hasCf.value ? [cfTotal(t.cf, money(t.cf))] : []), ...(hasKt.value && hasCf.value ? [signedMoney(t.cf_minus_kt)] : [])]
}

function exportCsv() {
  const d = data.value
  if (!d) return
  const header = ['Account', 'Team', 'In KH', 'Quantity', 'Avg sales/day', 'PL2 KT (est.)', 'PL2 CF (actual)', 'CF − KT']
  const line = (r: Pl2AccountLine, inKh: string) => [r.shop, r.team ?? '', inKh, r.quantity, perDayValue(r.quantity, days.value), r.kt ?? '',
    r.cf ?? '', r.cf_minus_kt ?? '']
  const body = [...d.accounts.map((a) => line(a, 'yes')), ...d.others.children.map((c) => line(c, 'no'))]
  downloadCsv(`pl2-by-account-${props.params.date_from}_${props.params.date_to}.csv`, header, body)
  ElMessage.success(`Exported ${body.length} accounts`)
}
</script>

<template>
  <div class="section-card">
    <div class="mb-1 flex flex-wrap items-center justify-between gap-3">
      <h3 class="card-title !mb-0">PL2 by account: KT vs CF</h3>
      <el-button size="small" type="success" plain :icon="Download" :disabled="!rows.length" @click="exportCsv">Export</el-button>
    </div>
    <div v-if="hasCf" class="mb-3 text-xs text-muted">{{ source }}</div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!my-3" />
    <template v-else-if="data">
      <el-alert v-if="data.kt.error" type="info" :closable="false" show-icon :title="data.kt.error" class="!my-3" />
      <el-alert v-if="!hasCf" type="info" :closable="false" show-icon :title="cf?.error" class="!my-3">
        <RouterLink v-if="auth.isAdmin.value && cf?.error?.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
      </el-alert>
      <el-alert v-for="w in cf?.warnings ?? []" :key="w" type="warning" :closable="false" show-icon :title="w" class="!my-3" />
    </template>

    <div v-loading="loading" class="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
      <div v-for="k in kpis" :key="k.label" class="kpi">
        <div class="kpi__label">{{ k.label }}</div>
        <div class="kpi__value" :style="k.color ? { color: k.color } : undefined">{{ k.value }}</div>
        <div v-if="k.hint" class="mt-1 text-xs text-muted">{{ k.hint }}</div>
      </div>
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
      <el-table-column v-if="hasKt" label="PL2 KT (est.)" prop="kt" min-width="120" align="right" sortable>
        <template #default="{ row }"><span class="num font-semibold">{{ row.kt == null ? '' : money(row.kt) }}</span></template>
      </el-table-column>
      <el-table-column v-if="hasCf" label="PL2 CF (actual)" prop="cf" min-width="125" align="right" sortable class-name="cf-cell">
        <template #default="{ row }"><span class="num" :style="{ color: cfColor(row.cf) }">{{ row.cf == null ? '' : money(row.cf) }}</span></template>
      </el-table-column>
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
      report's days (pieces added by hand, Felt, are not tied to an account). PL2 CF = finance's PROFIT THỰC ĐẠT of the account
      ("PL Account Etsy_Monthly"), booked per month: the range counts the whole months it touches. CF − KT = PL2 CF − PL2 KT.
    </div>
  </div>
</template>
