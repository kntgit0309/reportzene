<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { auth } from '../../lib/auth'
import { cfColor, gapColor, signedMoney } from '../../lib/plan'
import { money, moneyRound, num, pct } from '../../lib/format'
import { fetchPl2AccountTypes } from '../../lib/report'
import type { Pl2AccountLine, Pl2AccountMonth, Pl2Accounts, Pl2SellerNode, Pl2SellerProduct, Pl2SellerTypes } from '../../lib/types'

// Etsy › Report › PL2 by account: one card per account of the plans (PL2 KT, progress against the quarter's plan on the KT basis
// with a mark at the plan to date, PL2 CF against its own plan), a card for the other accounts, and a click opens the account's
// PL2 per month and its products. Under the cards, one table of every account's month: KH theo KT, PL2 KT, KH theo CF, PL2 CF,
// % of the CF plan to date and the account's share of the month's PL2 CF. The same as the seller cards.
const props = defineProps<{ data: Pl2Accounts; params: Record<string, string> }>()

const LOW = 0.8 // below 80% of the plan to date the bar turns red
const hasKt = computed(() => !props.data.kt.error)
const hasCf = computed(() => !props.data.cf.error)
const cards = computed(() => props.data.accounts.filter((a) => a.kt_plan_total != null))
const others = computed(() => (props.data.others.count ? props.data.others : null))
const visible = computed(() => hasKt.value && !props.data.kh_pl2?.error && cards.value.length > 0)
// why there are no cards, so that they are never just missing (the plan sheet is picked in Settings › Plan); the note of the filters
// that cut across stores is already CF's, above, and the KT error is the block's own
const reason = computed(() => {
  if (visible.value || props.data.kt.error) return ''
  const e = props.data.kh_pl2?.error
  if (e) return e === props.data.cf.error ? '' : e
  return 'The account PL2 plan sheet ("KH theo Acc") has no account with a plan for the months of this range'
})

// the bar: the quarter's plan is the full width, the fill is the PL2 KT so far and the mark is where the plan stands today
const share = (v: number | null | undefined, whole: number | null | undefined) =>
  v == null || !whole || whole <= 0 ? 0 : Math.max(0, Math.min(100, (v / whole) * 100))
const isLow = (a: Pl2AccountLine) => a.kt_pct != null && a.kt_pct < LOW
const dash = (v: number | null | undefined) => (v == null ? '—' : money(v))

// Theo tháng · từng account: a row per account of the plans, the other accounts together and the total, a group of columns per month
type MonthRow = { key: string; name: string; sub?: string | null; total?: boolean; months: Pl2AccountMonth[] }
const monthKeys = computed(() => (props.data.total.months ?? []).map((m) => m.month))
const monthRows = computed<MonthRow[]>(() => {
  const rows: MonthRow[] = cards.value.map((a) => ({ key: a.shop, name: a.shop, sub: a.team, months: a.months }))
  if (others.value?.months.length) rows.push({ key: '_other', name: 'Other accounts', months: others.value.months })
  rows.push({ key: '_total', name: 'Tổng', total: true, months: props.data.total.months })
  return rows
})
// the % of the plan and the share of the month are on PL2 CF, finance's figure (on PL2 KT while there is no CF)
const basis = computed<'cf' | 'kt'>(() => (hasCf.value ? 'cf' : 'kt'))
const basisLabel = computed(() => basis.value.toUpperCase())
const monthOf = (slot: unknown, month: string): Pl2AccountMonth =>
  (slot as MonthRow).months.find((m) => m.month === month) ?? { month, kt_plan: null, cf_plan: null, kt_plan_to_date: null, cf_plan_to_date: null, quantity: null, kt: null, cf: null }
const doneOf = (slot: unknown, month: string) => {
  const m = monthOf(slot, month)
  const v = m[basis.value]
  const plan = basis.value === 'cf' ? m.cf_plan_to_date : m.kt_plan_to_date
  return v == null || !plan ? null : v / plan // % HT theo CF: PL2 CF / the CF plan to date
}
const contribution = (slot: unknown, month: string) => {
  const total = props.data.total.months.find((m) => m.month === month)?.[basis.value]
  const v = monthOf(slot, month)[basis.value]
  return v == null || !total || total <= 0 ? null : v / total // the account's PL2 CF / every account's PL2 CF of the month
}
const doneColor = (v: number | null) => (v == null ? undefined : v >= 1 ? '#16a34a' : v < 0.85 ? '#dc2626' : undefined)
const monthRowClass = ({ row }: { row: MonthRow }) => (row.total ? 'month-total' : '')

// the dialog of a card: the account's months, and its products opened onto their product types and sub product types
const open = ref(false)
const picked = ref<Pl2AccountLine | null>(null)
const details = ref<Pl2SellerTypes | null>(null)
const detailsLoading = ref(false)
let ticket = 0
async function show(a: Pl2AccountLine) {
  picked.value = a
  details.value = null
  open.value = true
  if (!a.shop_ids?.length) return
  const mine = ++ticket
  detailsLoading.value = true
  try {
    const got = await fetchPl2AccountTypes({ ...props.params, shops: a.shop_ids.join(',') })
    if (mine === ticket) details.value = got
  } catch (e) {
    if (mine === ticket) ElMessage.error((e as Error).message)
  } finally {
    if (mine === ticket) detailsLoading.value = false
  }
}

type Row = Partial<Pl2AccountMonth> & { label: string; total?: boolean; ktPct?: number | null; cfPct?: number | null }
const ratio = (v: number | null | undefined, plan: number | null | undefined) => (v == null || !plan ? null : v / plan)
const pickedRows = computed<Row[]>(() => {
  const a = picked.value
  if (!a) return []
  const months: Row[] = a.months.map((m) => ({ ...m, label: `Tháng ${Number(m.month.slice(0, 2))}`, ktPct: ratio(m.kt, m.kt_plan_to_date), cfPct: ratio(m.cf, m.cf_plan_to_date) }))
  return [...months, { label: 'Tổng', total: true, kt_plan: a.kt_plan_total, cf_plan: a.cf_plan_total, kt_plan_to_date: a.kt_plan, cf_plan_to_date: a.cf_plan,
                       kt: a.kt, cf: a.cf, ktPct: a.kt_pct, cfPct: a.cf_pct }]
})
const pickedRowClass = ({ rowIndex, row }: { rowIndex: number; row: Row }) => (row.total ? 'month-total' : `month-${rowIndex % 3}`)

// per product: pieces and PL2 KT in each month; a product opens onto its product types and sub product types once the details are in
type ProductRow = { key: string; name: string; depth: number; product?: Pl2SellerProduct; node?: Pl2SellerNode; total?: boolean; children?: ProductRow[] }
function treeRows(nodes: Pl2SellerNode[], parent: string, depth: number): ProductRow[] {
  return nodes.map((node) => {
    const key = `${parent}/${node.name}`
    return { key, name: node.name, depth, node, children: node.children?.length ? treeRows(node.children, key, depth + 1) : undefined }
  })
}
const productRows = computed<ProductRow[]>(() => {
  const a = picked.value
  if (!a || !a.products.length) return []
  const kids = new Map((details.value?.products ?? []).map((p) => [p.name, p.children]))
  const top: ProductRow[] = a.products.map((product) => {
    const children = kids.get(product.name)
    return { key: product.name, name: product.name, depth: 0, product, children: children?.length ? treeRows(children, product.name, 1) : undefined }
  })
  return [...top, { key: '_total', name: 'Tổng', depth: 0, total: true }]
})
const productRowClass = ({ row }: { row: ProductRow }) => (row.total ? 'month-total' : row.depth ? 'child-row' : '')
// a month the range does not touch has no figures (null); a touched month without sales is 0
function cell(slot: unknown, month: Pl2AccountMonth): { quantity: number; kt: number } | null {
  const row = slot as ProductRow
  if (month.kt == null) return null
  if (row.total) return { quantity: month.quantity ?? 0, kt: month.kt }
  return (row.node ?? row.product)?.months[month.month] ?? { quantity: 0, kt: 0 }
}
function overall(slot: unknown): { quantity: number; kt: number } {
  const row = slot as ProductRow
  if (row.total) return { quantity: picked.value?.quantity ?? 0, kt: picked.value?.kt ?? 0 }
  const line = row.node ?? row.product
  return { quantity: line?.quantity ?? 0, kt: line?.kt ?? 0 }
}
const muted = (v: number | null | undefined) => (v ? '' : 'text-slate-300')
</script>

<template>
  <div v-if="!visible && reason && !auth.ownSalesOnly.value" class="mb-4">
    <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
      Theo account <span class="font-normal normal-case tracking-normal text-slate-400">· chưa có thẻ</span>
    </div>
    <el-alert type="info" :closable="false" show-icon :title="reason">
      <RouterLink v-if="auth.isAdmin.value" to="/settings" class="text-[#2563eb]">Open Settings → Plan (Account PL2 plan sheet)</RouterLink>
    </el-alert>
  </div>
  <div v-else-if="visible" class="mb-4">
    <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
      Theo account <span class="font-normal normal-case tracking-normal text-slate-400">· bấm vào ô để xem chi tiết theo tháng và theo product</span>
    </div>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <button v-for="a in cards" :key="a.shop" type="button" class="seller-card seller-card--click" @click="show(a)">
        <div class="flex items-baseline justify-between gap-2">
          <span class="truncate text-base font-semibold text-slate-900">{{ a.shop }}</span>
          <span v-if="a.team" class="shrink-0 text-xs text-slate-400">{{ a.team }}</span>
        </div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold text-slate-900">{{ money(a.kt) }}</span>
          <span class="text-xs text-slate-500">{{ num(a.quantity) }} pcs</span>
        </div>
        <div v-if="hasCf && a.cf != null" class="text-xs" :style="{ color: cfColor(a.cf) }">
          PL2 CF {{ money(a.cf) }}<span v-if="a.cf_pct != null" class="text-slate-400"> · {{ pct(a.cf_pct, 1) }} KH theo CF</span>
        </div>
        <div class="bar" :class="{ 'bar--low': isLow(a) }">
          <div class="bar__fill" :style="{ width: `${share(a.kt, a.kt_plan_total)}%` }" />
          <div v-if="a.kt_plan_total" class="bar__mark" :style="{ left: `${share(a.kt_plan, a.kt_plan_total)}%` }" title="KH lũy kế" />
        </div>
        <dl class="seller-card__rows">
          <div><dt>KH quý</dt><dd>{{ money(a.kt_plan_total) }}</dd></div>
          <div><dt>KH lũy kế</dt><dd>{{ money(a.kt_plan) }}</dd></div>
          <div><dt>% HT lũy kế</dt><dd class="font-semibold text-slate-900">{{ pct(a.kt_pct, 1) }}</dd></div>
        </dl>
      </button>
      <div v-if="others" class="seller-card">
        <div class="text-base font-semibold text-slate-900">Other accounts</div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold text-slate-900">{{ money(others.kt) }}</span>
          <span class="text-xs text-slate-500">{{ num(others.quantity) }} pcs</span>
        </div>
        <div v-if="hasCf && others.cf != null" class="text-xs" :style="{ color: cfColor(others.cf) }">PL2 CF {{ money(others.cf) }}</div>
        <div class="mt-3 text-xs text-slate-400">Account ngoài kế hoạch ({{ others.count }} account có PL2)</div>
      </div>
    </div>

    <div class="mb-2 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-500">Theo tháng <span class="font-normal normal-case tracking-normal text-slate-400">· từng account</span></div>
    <el-table :data="monthRows" row-key="key" :row-class-name="monthRowClass" size="small" border class="w-full">
      <el-table-column label="Account" min-width="190" fixed>
        <template #default="{ row }">
          <b v-if="row.total">{{ row.name }}</b>
          <template v-else><span class="font-medium text-slate-800">{{ row.name }}</span> <span v-if="row.sub" class="text-xs text-slate-400">{{ row.sub }}</span></template>
        </template>
      </el-table-column>
      <el-table-column v-for="(k, i) in monthKeys" :key="k" :label="`Tháng ${Number(k.slice(0, 2))}`" align="center" :label-class-name="`mh-${i % 3}`">
        <el-table-column label="KH theo KT" align="right" width="100" :class-name="`mt-${i % 3} mt-first`" :label-class-name="`mh-${i % 3}`">
          <template #default="{ row }"><span class="num text-slate-600">{{ dash(monthOf(row, k).kt_plan) }}</span></template>
        </el-table-column>
        <el-table-column label="PL2 KT" align="right" width="100" :class-name="`mt-${i % 3}`" :label-class-name="`mh-${i % 3}`">
          <template #default="{ row }"><span class="num font-semibold">{{ dash(monthOf(row, k).kt) }}</span></template>
        </el-table-column>
        <el-table-column v-if="hasCf" label="KH theo CF" align="right" width="100" :class-name="`mt-${i % 3}`" :label-class-name="`mh-${i % 3}`">
          <template #default="{ row }"><span class="num text-slate-600">{{ dash(monthOf(row, k).cf_plan) }}</span></template>
        </el-table-column>
        <el-table-column v-if="hasCf" label="PL2 CF" align="right" width="100" :class-name="`mt-${i % 3}`" :label-class-name="`mh-${i % 3}`">
          <template #default="{ row }"><span class="num" :style="{ color: cfColor(monthOf(row, k).cf) }">{{ dash(monthOf(row, k).cf) }}</span></template>
        </el-table-column>
        <el-table-column :label="`% HT theo ${basisLabel}*`" align="right" width="92" :class-name="`mt-${i % 3}`" :label-class-name="`mh-${i % 3}`">
          <template #default="{ row }"><span class="num font-semibold" :style="{ color: doneColor(doneOf(row, k)) }">{{ pct(doneOf(row, k), 1) }}</span></template>
        </el-table-column>
        <el-table-column label="Tỷ trọng đóng góp" align="right" width="96" :class-name="`mt-${i % 3}`" :label-class-name="`mh-${i % 3}`">
          <template #default="{ row }"><span class="num text-slate-600">{{ pct(contribution(row, k), 1) }}</span></template>
        </el-table-column>
      </el-table-column>
    </el-table>
    <div class="mt-2 text-xs text-slate-400">
      KH theo KT / KH theo CF = PL2 của tháng trong KHKD "KH theo Acc" (khối PL2 theo KT và PL2 theo CF), PL2 KT = quantity × PL2/item của kế hoạch,
      PL2 CF = PROFIT THỰC ĐẠT của tài chính (tính theo tháng). * % HT theo {{ basisLabel }} = PL2 {{ basisLabel }} / KH theo {{ basisLabel }} đến hết khoảng ngày đang chọn
      (tháng đã trọn thì là cả tháng); Tỷ trọng đóng góp = PL2 {{ basisLabel }} của account / tổng PL2 {{ basisLabel }} của mọi account trong tháng. CF ghi theo tháng nên
      so với kế hoạch đến hết khoảng ngày chỉ sát khi khoảng ngày bắt đầu từ đầu tháng; CF âm của các account khác có thể làm tỷ trọng của account vượt 100%.
      Tháng ngoài khoảng ngày chỉ có kế hoạch (—).
    </div>

    <el-dialog v-model="open" :title="`Account ${picked?.shop ?? ''}`" width="min(1100px, 96vw)">
      <template v-if="picked">
        <div class="mb-1 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm text-slate-600">
          <span>PL2 KT <b class="text-slate-900">{{ money(picked.kt) }}</b> · {{ num(picked.quantity) }} pcs</span>
          <span>KH quý <b class="text-slate-900">{{ money(picked.kt_plan_total) }}</b></span>
          <span>KH lũy kế <b class="text-slate-900">{{ money(picked.kt_plan) }}</b></span>
          <b :style="{ color: gapColor(picked.kt_pct == null ? null : picked.kt_pct - 1) }">{{ pct(picked.kt_pct, 1) }}</b>
        </div>
        <div v-if="hasCf" class="mb-3 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm text-slate-600">
          <span>PL2 CF <b :style="{ color: cfColor(picked.cf) }">{{ money(picked.cf) }}</b></span>
          <span>KH quý (CF) <b class="text-slate-900">{{ money(picked.cf_plan_total) }}</b></span>
          <span>KH lũy kế (CF) <b class="text-slate-900">{{ money(picked.cf_plan) }}</b></span>
          <b :style="{ color: gapColor(picked.cf_pct == null ? null : picked.cf_pct - 1) }">{{ pct(picked.cf_pct, 1) }}</b>
        </div>
        <div class="mb-1 mt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Theo tháng</div>
        <el-table :data="pickedRows" :row-class-name="pickedRowClass" size="small" class="w-full">
          <el-table-column prop="label" label="" width="80"><template #default="{ row }"><b>{{ row.label }}</b></template></el-table-column>
          <el-table-column label="KH theo KT" align="right"><template #default="{ row }"><span class="num">{{ dash(row.kt_plan) }}</span></template></el-table-column>
          <el-table-column label="KH LK" align="right"><template #default="{ row }"><span class="num text-slate-500">{{ dash(row.kt_plan_to_date) }}</span></template></el-table-column>
          <el-table-column label="PL2 KT" align="right"><template #default="{ row }"><span class="num font-semibold">{{ dash(row.kt) }}</span></template></el-table-column>
          <el-table-column label="% HT KT" align="right" width="80"><template #default="{ row }"><span class="num text-slate-500">{{ pct(row.ktPct, 1) }}</span></template></el-table-column>
          <template v-if="hasCf">
            <el-table-column label="KH theo CF" align="right"><template #default="{ row }"><span class="num">{{ dash(row.cf_plan) }}</span></template></el-table-column>
            <el-table-column label="KH LK" align="right"><template #default="{ row }"><span class="num text-slate-500">{{ dash(row.cf_plan_to_date) }}</span></template></el-table-column>
            <el-table-column label="PL2 CF" align="right"><template #default="{ row }"><span class="num" :style="{ color: cfColor(row.cf) }">{{ dash(row.cf) }}</span></template></el-table-column>
            <el-table-column label="% HT CF" align="right" width="80"><template #default="{ row }"><span class="num text-slate-500">{{ pct(row.cfPct, 1) }}</span></template></el-table-column>
            <el-table-column label="CF − KT" align="right">
              <template #default="{ row }">
                <span class="num" :style="{ color: gapColor(row.kt == null || row.cf == null ? null : row.cf - row.kt) }">
                  {{ row.kt == null || row.cf == null ? '—' : signedMoney(row.cf - row.kt) }}
                </span>
              </template>
            </el-table-column>
          </template>
        </el-table>

        <template v-if="productRows.length">
          <div class="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Theo product <span class="font-normal normal-case tracking-normal text-slate-400">· số KT: sales (pcs) và PL2 theo KT · bấm ▸ để xem product type và sub product type</span>
          </div>
          <el-table v-loading="detailsLoading" :data="productRows" row-key="key" :tree-props="{ children: 'children' }"
                    :row-class-name="productRowClass" size="small" class="w-full" border>
            <el-table-column prop="name" label="Product" min-width="200">
              <template #default="{ row }"><span :class="row.depth ? 'text-slate-600' : 'font-bold'">{{ row.name }}</span></template>
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
          KH theo KT / CF = PL2 của tháng trong KHKD "KH theo Acc"; KH LK = kế hoạch đến hết khoảng ngày đang chọn (tháng lẻ theo ngày). PL2 KT của các ngày trong khoảng;
          tháng ngoài khoảng ngày không có số (—). PL2 CF là số tài chính ghi theo tháng, tính trọn các tháng mà khoảng ngày chạm tới. Một account có thể gồm store bị
          tạm ngưng đã chuyển sang account thay thế (Settings › Plan).
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
