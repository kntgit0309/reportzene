<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { auth } from '../../lib/auth'
import { dateTime, money, moneyRound, num, pct } from '../../lib/format'
import { gapColor, signedMoney } from '../../lib/plan'
import { fetchProductAccounts, fetchProductMonths, fetchProductTypes } from '../../lib/report'
import type { Pl2SellerNode, ProductAccounts, ProductMonth, ProductMonthLine, ProductMonths, ProductTypes } from '../../lib/types'

// Etsy › Report: one card per product of the business plan (PL2 KT, progress against the quarter's plan with a mark at the plan to
// date), a click opens the product's PL2 per month, its product types and its accounts; under the cards, one table of every product's month:
// plan, PL2 KT, % of the plan to date and the product's share of the month's PL2 KT. The same as the seller cards.
const props = defineProps<{ params: Record<string, string> }>()
const data = ref<ProductMonths | null>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await fetchProductMonths(props.params)
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

const LOW = 0.8 // below 80% of the plan to date the bar turns red
const products = computed(() => data.value?.products ?? [])
const hasCards = computed(() => products.value.length > 0 && !data.value?.plan.error)
const source = computed(() => {
  const p = data.value?.plan
  if (!p?.sheet) return ''
  return `Plan: ${p.sheet.name.trim()} · ${p.sheet.tab_title.trim()} · synced ${dateTime(p.sheet.last_synced_at)}${p.scope && p.scope !== 'ZenE' ? ` · ${p.scope}` : ''}`
})
const notes = computed(() => (data.value?.plan.missing?.length ? [`The plan sheet has no plan for ${data.value.plan.missing.join(', ')}`] : []))

// the bar: the quarter's plan is the full width, the fill is the PL2 KT so far and the mark is where the plan stands today
const share = (v: number | null | undefined, whole: number | null | undefined) =>
  v == null || !whole || whole <= 0 ? 0 : Math.max(0, Math.min(100, (v / whole) * 100))
const isLow = (p: ProductMonthLine) => p.kt_pct != null && p.kt_pct < LOW
const dash = (v: number | null | undefined) => (v == null ? '—' : money(v))

// Theo tháng · từng product: a row per product, the total, a group of columns per month
type MonthRow = { key: string; name: string; total?: boolean; line: ProductMonthLine }
const monthKeys = computed(() => (data.value?.total?.months ?? []).map((m) => m.month))
const monthRows = computed<MonthRow[]>(() => {
  const t = data.value?.total
  if (!t) return []
  return [...products.value.map((line) => ({ key: line.name, name: line.name, line })), { key: '_total', name: 'Tổng', total: true, line: t }]
})
const monthOf = (slot: unknown, month: string): ProductMonth =>
  (slot as MonthRow).line.months.find((m) => m.month === month) ?? { month, plan: null, plan_to_date: null, quantity: null, kt: null }
const doneOf = (slot: unknown, month: string) => {
  const m = monthOf(slot, month)
  return m.kt == null || !m.plan_to_date ? null : m.kt / m.plan_to_date // % HT theo KT: PL2 KT / the plan to date
}
const contribution = (slot: unknown, month: string) => {
  const total = data.value?.total?.months.find((m) => m.month === month)?.kt
  const kt = monthOf(slot, month).kt
  return kt == null || !total || total <= 0 ? null : kt / total
}
const doneColor = (v: number | null) => (v == null ? undefined : v >= 1 ? '#16a34a' : v < 0.85 ? '#dc2626' : undefined)
const monthRowClass = ({ row }: { row: MonthRow }) => (row.total ? 'month-total' : '')

// the dialog of a card: the product's months, its product types and sub product types, and its accounts, asked when the card is opened
const open = ref(false)
const picked = ref<ProductMonthLine | null>(null)
const details = ref<ProductTypes | null>(null)
const detailsLoading = ref(false)
const accounts = ref<ProductAccounts | null>(null)
const accountsLoading = ref(false)
let ticket = 0
async function show(p: ProductMonthLine) {
  picked.value = p
  details.value = null
  accounts.value = null
  open.value = true
  const mine = ++ticket
  detailsLoading.value = true
  accountsLoading.value = true
  const query = { ...props.params, product: p.name }
  // two asks side by side: one failing leaves the other table
  const run = async <T,>(fetch: () => Promise<T>, into: (v: T) => void, done: () => void) => {
    try {
      const got = await fetch()
      if (mine === ticket) into(got)
    } catch (e) {
      if (mine === ticket) ElMessage.error((e as Error).message)
    } finally {
      if (mine === ticket) done()
    }
  }
  await Promise.all([
    run(() => fetchProductTypes(query), (v) => (details.value = v), () => (detailsLoading.value = false)),
    run(() => fetchProductAccounts(query), (v) => (accounts.value = v), () => (accountsLoading.value = false)),
  ])
}

type PickedRow = Partial<ProductMonth> & { label: string; total?: boolean; ktPct?: number | null }
const ratio = (v: number | null | undefined, plan: number | null | undefined) => (v == null || !plan ? null : v / plan)
const pickedRows = computed<PickedRow[]>(() => {
  const p = picked.value
  if (!p) return []
  const months: PickedRow[] = p.months.map((m) => ({ ...m, label: `Tháng ${Number(m.month.slice(0, 2))}`, ktPct: ratio(m.kt, m.plan_to_date) }))
  return [...months, { label: 'Tổng', total: true, plan: p.plan_total, plan_to_date: p.plan, kt: p.kt, quantity: p.quantity, ktPct: p.kt_pct }]
})
const pickedRowClass = ({ rowIndex, row }: { rowIndex: number; row: PickedRow }) => (row.total ? 'month-total' : `month-${rowIndex % 3}`)

type TreeRow = { key: string; name: string; depth: number; node?: Pl2SellerNode; total?: boolean; children?: TreeRow[] }
function treeRows(nodes: Pl2SellerNode[], parent: string, depth: number): TreeRow[] {
  return nodes.map((node) => {
    const key = `${parent}/${node.name}`
    return { key, name: node.name, depth, node, children: node.children?.length ? treeRows(node.children, key, depth + 1) : undefined }
  })
}
const withTotal = (nodes: Pl2SellerNode[] | undefined): TreeRow[] =>
  nodes?.length ? [...treeRows(nodes, '', 0), { key: '_total', name: 'Tổng', depth: 0, total: true }] : []
const typeRows = computed<TreeRow[]>(() => withTotal(details.value?.children))
const accountRows = computed<TreeRow[]>(() => withTotal(accounts.value?.children))
// the two tables of the dialog under the months: the same columns (sales and PL2 KT per month, then the total), other rows
const breakdowns = computed(() => [
  { key: 'types', title: 'Theo product type', label: 'Product type / sub product type', rows: typeRows.value, loading: detailsLoading.value,
    hint: '· số KT: sales (pcs) và PL2 theo KT · bấm ▸ để xem sub product type', empty: 'Chưa có product type nào bán trong khoảng ngày này', maxHeight: undefined },
  { key: 'accounts', title: 'Theo account', label: 'Account', rows: accountRows.value, loading: accountsLoading.value, maxHeight: 460,
    hint: accounts.value ? `· ${num(accounts.value.count)} account có bán · sales (pcs) và PL2 theo KT, lớn nhất trước` : '· sales (pcs) và PL2 theo KT, lớn nhất trước',
    empty: 'Chưa có account nào bán product này trong khoảng ngày này' },
])
const typeRowClass = ({ row }: { row: TreeRow }) => (row.total ? 'month-total' : row.depth ? 'child-row' : '')
// a month the range does not touch has no figures (null); a touched month without sales is 0
function cell(slot: unknown, month: ProductMonth): { quantity: number; kt: number } | null {
  const row = slot as TreeRow
  if (month.kt == null) return null
  if (row.total) return { quantity: month.quantity ?? 0, kt: month.kt }
  return row.node?.months[month.month] ?? { quantity: 0, kt: 0 }
}
function overall(slot: unknown): { quantity: number; kt: number } {
  const row = slot as TreeRow
  if (row.total) return { quantity: picked.value?.quantity ?? 0, kt: picked.value?.kt ?? 0 }
  return { quantity: row.node?.quantity ?? 0, kt: row.node?.kt ?? 0 }
}
const muted = (v: number | null | undefined) => (v ? '' : 'text-slate-300')
</script>

<template>
  <div class="section-card">
    <h3 class="card-title !mb-1">PL2 by product: KT vs plan</h3>
    <div v-if="source" class="mb-3 text-xs text-muted">{{ source }}</div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!my-3" />
    <template v-else-if="data">
      <el-alert v-if="data.plan.error && !auth.ownSalesOnly.value" type="info" :closable="false" show-icon :title="data.plan.error" class="!my-3">
        <RouterLink v-if="auth.isAdmin.value && data.plan.error.includes('Settings')" to="/settings" class="text-[#2563eb]">Open Settings → Plan</RouterLink>
      </el-alert>
      <el-alert v-for="n in notes" :key="n" type="warning" :closable="false" show-icon :title="n" class="!my-3" />
    </template>

    <div v-loading="loading" :class="{ 'min-h-16': loading && !data }">
      <template v-if="hasCards">
        <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Theo product <span class="font-normal normal-case tracking-normal text-slate-400">· bấm vào ô để xem chi tiết theo tháng và theo product type</span>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <button v-for="p in products" :key="p.name" type="button" class="seller-card seller-card--click" @click="show(p)">
            <div class="truncate text-base font-semibold text-slate-900">{{ p.name }}</div>
            <div class="mt-1 flex items-baseline gap-2">
              <span class="text-2xl font-bold text-slate-900">{{ money(p.kt) }}</span>
              <span class="text-xs text-slate-500">{{ num(p.quantity) }} pcs</span>
            </div>
            <template v-if="p.in_plan">
              <div class="bar" :class="{ 'bar--low': isLow(p) }">
                <div class="bar__fill" :style="{ width: `${share(p.kt, p.plan_total)}%` }" />
                <div v-if="p.plan_total" class="bar__mark" :style="{ left: `${share(p.plan, p.plan_total)}%` }" title="KH lũy kế" />
              </div>
              <dl class="seller-card__rows">
                <div><dt>KH quý</dt><dd>{{ money(p.plan_total) }}</dd></div>
                <div><dt>KH lũy kế</dt><dd>{{ money(p.plan) }}</dd></div>
                <div><dt>% HT lũy kế</dt><dd class="font-semibold text-slate-900">{{ pct(p.kt_pct, 1) }}</dd></div>
              </dl>
            </template>
            <div v-else class="mt-3 text-xs text-slate-400">Không có dòng kế hoạch: PL2 KT tính theo PL2/item ở Settings › Plan</div>
          </button>
        </div>

        <div class="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-500">Theo tháng <span class="font-normal normal-case tracking-normal text-slate-400">· từng product</span></div>
        <el-table :data="monthRows" row-key="key" :row-class-name="monthRowClass" size="small" border class="w-full">
          <el-table-column label="Product" min-width="170" fixed>
            <template #default="{ row }"><b v-if="row.total">{{ row.name }}</b><span v-else class="font-medium text-slate-800">{{ row.name }}</span></template>
          </el-table-column>
          <el-table-column v-for="(k, i) in monthKeys" :key="k" :label="`Tháng ${Number(k.slice(0, 2))}`" align="center" :label-class-name="`mh-${i % 3}`">
            <el-table-column label="Kế hoạch" align="right" width="100" :class-name="`mt-${i % 3} mt-first`" :label-class-name="`mh-${i % 3}`">
              <template #default="{ row }"><span class="num text-slate-600">{{ dash(monthOf(row, k).plan) }}</span></template>
            </el-table-column>
            <el-table-column label="PL2 KT" align="right" width="100" :class-name="`mt-${i % 3}`" :label-class-name="`mh-${i % 3}`">
              <template #default="{ row }"><span class="num font-semibold">{{ dash(monthOf(row, k).kt) }}</span></template>
            </el-table-column>
            <el-table-column label="% HT theo KT*" align="right" width="92" :class-name="`mt-${i % 3}`" :label-class-name="`mh-${i % 3}`">
              <template #default="{ row }"><span class="num font-semibold" :style="{ color: doneColor(doneOf(row, k)) }">{{ pct(doneOf(row, k), 1) }}</span></template>
            </el-table-column>
            <el-table-column label="Tỷ trọng đóng góp" align="right" width="96" :class-name="`mt-${i % 3}`" :label-class-name="`mh-${i % 3}`">
              <template #default="{ row }"><span class="num text-slate-600">{{ pct(contribution(row, k), 1) }}</span></template>
            </el-table-column>
          </el-table-column>
        </el-table>
        <div class="mt-2 text-xs text-slate-400">
          Kế hoạch = PL2 của tháng trong KHKD "KH theo Product" (Settings › Plan). * % HT theo KT = PL2 KT / kế hoạch đến hết khoảng ngày đang chọn (tháng đã trọn thì là cả tháng).
          Tỷ trọng đóng góp = PL2 KT của product / tổng PL2 KT của mọi product trong tháng. PL2 KT = quantity × PL2/item của kế hoạch (Other products theo Settings › Plan),
          gồm phần cộng tay (Felt). Tháng ngoài khoảng ngày chỉ có kế hoạch (—). Kế hoạch là của cả ZenE nên bỏ khi lọc team, store, designer hoặc keyword.
        </div>
      </template>
    </div>

    <el-dialog v-model="open" :title="`Product ${picked?.name ?? ''}`" width="min(1040px, 96vw)">
      <template v-if="picked">
        <div class="mb-3 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm text-slate-600">
          <span>Thực đạt <b class="text-slate-900">{{ money(picked.kt) }}</b> · {{ num(picked.quantity) }} pcs</span>
          <template v-if="picked.in_plan">
            <span>KH quý <b class="text-slate-900">{{ money(picked.plan_total) }}</b></span>
            <span>KH lũy kế <b class="text-slate-900">{{ money(picked.plan) }}</b></span>
            <b :style="{ color: gapColor(picked.kt_pct == null ? null : picked.kt_pct - 1) }">{{ pct(picked.kt_pct, 1) }}</b>
          </template>
        </div>
        <div class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Theo tháng</div>
        <el-table :data="pickedRows" :row-class-name="pickedRowClass" size="small" class="w-full">
          <el-table-column prop="label" label="" width="90"><template #default="{ row }"><b>{{ row.label }}</b></template></el-table-column>
          <el-table-column label="Kế hoạch" align="right"><template #default="{ row }"><span class="num">{{ dash(row.plan) }}</span></template></el-table-column>
          <el-table-column label="KH LK" align="right"><template #default="{ row }"><span class="num text-slate-500">{{ dash(row.plan_to_date) }}</span></template></el-table-column>
          <el-table-column label="Thực đạt (KT)" align="right"><template #default="{ row }"><span class="num font-semibold">{{ dash(row.kt) }}</span></template></el-table-column>
          <el-table-column label="Sales" align="right" width="90">
            <template #default="{ row }"><span class="num">{{ row.quantity == null ? '—' : num(row.quantity) }}</span></template>
          </el-table-column>
          <el-table-column label="% HT" align="right" width="80">
            <template #default="{ row }"><span class="num text-slate-500">{{ pct(row.ktPct, 1) }}</span></template>
          </el-table-column>
          <el-table-column label="KT − KH LK" align="right">
            <template #default="{ row }">
              <span class="num" :style="{ color: gapColor(row.kt == null || row.plan_to_date == null ? null : row.kt - row.plan_to_date) }">
                {{ row.kt == null || row.plan_to_date == null ? '—' : signedMoney(row.kt - row.plan_to_date) }}
              </span>
            </template>
          </el-table-column>
        </el-table>

        <template v-for="b in breakdowns" :key="b.key">
          <div class="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {{ b.title }} <span class="font-normal normal-case tracking-normal text-slate-400">{{ b.hint }}</span>
          </div>
          <el-table v-loading="b.loading" :data="b.rows" row-key="key" :tree-props="{ children: 'children' }" :row-class-name="typeRowClass"
                    :max-height="b.maxHeight" size="small" class="w-full" border :empty-text="b.empty">
            <el-table-column prop="name" :label="b.label" min-width="220">
              <template #default="{ row }"><span :class="row.depth ? 'text-slate-600' : 'font-semibold'">{{ row.name }}</span></template>
            </el-table-column>
            <el-table-column v-for="(m, i) in picked.months" :key="m.month" :label="`Tháng ${Number(m.month.slice(0, 2))}`" align="center"
                             :label-class-name="`mh-${i % 3}`">
              <el-table-column label="Sales" align="right" width="76" :label-class-name="`mh-${i % 3}`">
                <template #default="{ row }"><span class="num" :class="muted(cell(row, m)?.quantity)">{{ cell(row, m) ? num(cell(row, m)!.quantity) : '—' }}</span></template>
              </el-table-column>
              <el-table-column label="PL2 KT" align="right" width="96" :label-class-name="`mh-${i % 3}`">
                <template #default="{ row }"><span class="num font-semibold" :class="muted(cell(row, m)?.kt)">{{ cell(row, m) ? moneyRound(cell(row, m)!.kt) : '—' }}</span></template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="Tổng" align="center" label-class-name="mh-total">
              <el-table-column label="Sales" align="right" width="76" label-class-name="mh-total">
                <template #default="{ row }"><span class="num" :class="muted(overall(row).quantity)">{{ num(overall(row).quantity) }}</span></template>
              </el-table-column>
              <el-table-column label="PL2 KT" align="right" width="96" label-class-name="mh-total">
                <template #default="{ row }"><span class="num font-semibold" :class="muted(overall(row).kt)">{{ moneyRound(overall(row).kt) }}</span></template>
              </el-table-column>
            </el-table-column>
          </el-table>
        </template>
        <div class="mt-2 text-xs text-slate-400">
          Kế hoạch = PL2 của tháng trong KHKD; KH LK = kế hoạch đến hết khoảng ngày đang chọn (tháng lẻ theo ngày). Thực đạt = PL2 KT của các ngày trong khoảng;
          tháng ngoài khoảng ngày không có số (—). Sub product type không bán thì ẩn; product type của trang vẫn hiện (0). Theo account = store của trackingis
          (store tạm ngưng tính vào store thay thế ở Settings › Plan); phần cộng tay (Felt) không thuộc account nào nên là dòng riêng, để Tổng khớp với thẻ.
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.seller-card { display: block; width: 100%; text-align: left; background: #fff; border: 1px solid var(--el-border-color); border-top: 3px solid var(--el-color-primary);
  border-radius: 12px; padding: 14px 16px; box-shadow: var(--skin-shadow-xs); font: inherit; color: inherit; }
.seller-card--click { cursor: pointer; transition: box-shadow 0.15s, transform 0.15s; }
.seller-card--click:hover { box-shadow: 0 6px 16px -6px #0f172a33; transform: translateY(-1px); }
.seller-card--click:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.bar { position: relative; height: 8px; margin: 10px 0 12px; background: #dbe1ea; border-radius: 999px; }
.bar__fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #1d4ed8, #60a5fa); }
.bar--low .bar__fill { background: linear-gradient(90deg, #b91c1c, #f87171); }
.bar__mark { position: absolute; top: -3px; width: 2px; height: 14px; margin-left: -1px; background: #f59e0b; border-radius: 1px; }
.seller-card__rows { margin: 0; display: grid; gap: 2px; font-size: 12px; color: var(--el-text-color-secondary); }
.seller-card__rows > div { display: flex; justify-content: space-between; }
.seller-card__rows dt, .seller-card__rows dd { margin: 0; }
.seller-card__rows dd { color: var(--el-text-color-regular); font-weight: 600; font-variant-numeric: tabular-nums; }
:deep(th.mh-0) { color: #1d4ed8 !important; background: #eaf1ff !important; }
:deep(th.mh-1) { color: #15803d !important; background: #e8f8ee !important; }
:deep(th.mh-2) { color: #c2410c !important; background: #fff4e5 !important; }
:deep(th.mh-total) { color: #0f172a !important; background: #eef1f6 !important; }
:deep(.month-0 td:first-child) { border-left: 4px solid #2563eb; }
:deep(.month-1 td:first-child) { border-left: 4px solid #16a34a; }
:deep(.month-2 td:first-child) { border-left: 4px solid #ea580c; }
:deep(.child-row td) { background: #fafbfd; }
:deep(td.mt-0) { background: #f5f8ff; }
:deep(td.mt-1) { background: #f1faf4; }
:deep(td.mt-2) { background: #fffbea; }
:deep(td.mt-first) { border-left: 3px solid; }
:deep(td.mt-0.mt-first) { border-left-color: #2563eb; }
:deep(td.mt-1.mt-first) { border-left-color: #16a34a; }
:deep(td.mt-2.mt-first) { border-left-color: #ea580c; }
:deep(.month-total td) { background: #f6f8fb !important; font-weight: 600; }
</style>
