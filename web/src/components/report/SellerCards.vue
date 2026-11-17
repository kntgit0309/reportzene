<script setup lang="ts">
import { computed, ref } from 'vue'
import { money, moneyRound, num, pct } from '../../lib/format'
import { cfColor, gapColor, signedMoney } from '../../lib/plan'
import type { Pl2SellerLine, Pl2SellerMonth, Pl2SellerProduct, Pl2Sellers } from '../../lib/types'

// Etsy › Report › PL2 by seller: one card per seller of the plan (PL2 KT, progress against the quarter's plan with a mark at the
// plan to date), a card for the other sellers, and a click opens the seller's PL2 per month.
const props = defineProps<{ data: Pl2Sellers }>()

const LOW = 0.8 // below 80% of the plan to date the bar turns red
const hasKt = computed(() => !props.data.kt.error)
const hasCf = computed(() => !props.data.cf.error)
const planned = computed(() => !props.data.plan.error && props.data.total.plan != null)
const sellers = computed(() => props.data.sellers.filter((s) => s.in_plan))
const others = computed(() => {
  const rest = props.data.sellers.filter((s) => !s.in_plan)
  if (!rest.length) return null
  const sum = (f: (s: Pl2SellerLine) => number | null) => rest.reduce((t, s) => t + (f(s) ?? 0), 0)
  return { count: rest.length, kt: sum((s) => s.kt), quantity: sum((s) => s.quantity), cf: hasCf.value ? sum((s) => s.cf) : null }
})
const visible = computed(() => hasKt.value && planned.value && sellers.value.length > 0)

// the bar: the quarter's plan is the full width, the fill is the PL2 KT so far and the mark is where the plan stands today
const share = (v: number | null | undefined, whole: number | null | undefined) =>
  v == null || !whole || whole <= 0 ? 0 : Math.max(0, Math.min(100, (v / whole) * 100))
const isLow = (s: Pl2SellerLine) => s.kt_pct != null && s.kt_pct < LOW
const subtitle = (s: Pl2SellerLine) => (s.sellers.length && s.sellers.join(' + ') !== s.seller ? s.sellers.join(' + ') : '')

const open = ref(false)
const picked = ref<Pl2SellerLine | null>(null)
function show(s: Pl2SellerLine) {
  picked.value = s
  open.value = true
}

type Row = Partial<Pl2SellerMonth> & { label: string; total?: boolean; cfPct?: number | null; ktPct?: number | null }
const ratio = (v: number | null | undefined, plan: number | null | undefined) => (v == null || !plan ? null : v / plan)
const rows = computed<Row[]>(() => {
  const s = picked.value
  if (!s) return []
  const months: Row[] = s.months.map((m) => ({
    ...m, label: `Tháng ${Number(m.month.slice(0, 2))}`, ktPct: ratio(m.kt, m.plan_to_date), cfPct: ratio(m.cf, m.plan_to_date),
  }))
  return [...months, { label: 'Tổng', total: true, plan: s.plan_total, plan_to_date: s.plan, kt: s.kt, cf: s.cf, ktPct: s.kt_pct, cfPct: s.cf_pct }]
})
const rowClass = ({ rowIndex, row }: { rowIndex: number; row: Row }) => (row.total ? 'month-total' : `month-${rowIndex % 3}`)
const dash = (v: number | null | undefined) => (v == null ? '—' : money(v))

// per product: pieces and PL2 KT in each month, as the plan's products in the plan's order (only KT: the plan has no product per seller)
type ProductRow = { name: string; product?: Pl2SellerProduct; total?: boolean }
const productRows = computed<ProductRow[]>(() => {
  const s = picked.value
  if (!s || !s.products.length) return []
  return [...s.products.map((product) => ({ name: product.name, product })), { name: 'Tổng', total: true }]
})
const productRowClass = ({ row }: { row: ProductRow }) => (row.total ? 'month-total' : '')
// a month the range does not touch has no figures (null); a touched month without sales is 0
function cell(slot: unknown, month: Pl2SellerMonth): { quantity: number; kt: number } | null {
  const row = slot as ProductRow // the table's slot row is untyped
  if (month.kt == null) return null
  if (row.total) return { quantity: month.quantity ?? 0, kt: month.kt }
  return row.product?.months[month.month] ?? { quantity: 0, kt: 0 }
}
function overall(slot: unknown): { quantity: number; kt: number } {
  const row = slot as ProductRow
  return row.total ? { quantity: picked.value?.quantity ?? 0, kt: picked.value?.kt ?? 0 } : { quantity: row.product?.quantity ?? 0, kt: row.product?.kt ?? 0 }
}
const muted = (v: number | null | undefined) => (v ? '' : 'text-slate-300')
</script>

<template>
  <div v-if="visible" class="mb-4">
    <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
      Theo seller <span class="font-normal normal-case tracking-normal text-slate-400">· bấm vào ô để xem chi tiết theo tháng</span>
    </div>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <button v-for="s in sellers" :key="s.seller" type="button" class="seller-card seller-card--click" @click="show(s)">
        <div class="flex items-baseline justify-between gap-2">
          <span class="truncate text-base font-semibold text-slate-900">{{ s.seller }}</span>
          <span v-if="subtitle(s)" class="truncate text-xs text-slate-400">{{ subtitle(s) }}</span>
        </div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold text-slate-900">{{ money(s.kt) }}</span>
          <span class="text-xs text-slate-500">{{ num(s.quantity) }} pcs</span>
        </div>
        <div v-if="hasCf && s.cf != null" class="text-xs" :style="{ color: cfColor(s.cf) }">PL2 CF {{ money(s.cf) }}</div>
        <div class="bar" :class="{ 'bar--low': isLow(s) }">
          <div class="bar__fill" :style="{ width: `${share(s.kt, s.plan_total)}%` }" />
          <div v-if="s.plan_total" class="bar__mark" :style="{ left: `${share(s.plan, s.plan_total)}%` }" title="KH lũy kế" />
        </div>
        <dl class="seller-card__rows">
          <div><dt>KH quý</dt><dd>{{ money(s.plan_total) }}</dd></div>
          <div><dt>KH lũy kế</dt><dd>{{ money(s.plan) }}</dd></div>
          <div><dt>% HT lũy kế</dt><dd class="font-semibold text-slate-900">{{ pct(s.kt_pct, 1) }}</dd></div>
        </dl>
      </button>
      <div v-if="others" class="seller-card">
        <div class="text-base font-semibold text-slate-900">Seller khác</div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold text-slate-900">{{ money(others.kt) }}</span>
          <span class="text-xs text-slate-500">{{ num(others.quantity) }} pcs</span>
        </div>
        <div v-if="hasCf && others.cf != null" class="text-xs" :style="{ color: cfColor(others.cf) }">PL2 CF {{ money(others.cf) }}</div>
        <div class="mt-3 text-xs text-slate-400">Seller ngoài danh sách {{ sellers.length }} người của kế hoạch ({{ others.count }} seller có PL2)</div>
      </div>
    </div>

    <el-dialog v-model="open" :title="`Seller ${picked?.seller ?? ''}`" width="min(1040px, 96vw)">
      <template v-if="picked">
        <div class="mb-3 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm text-slate-600">
          <span>Thực đạt <b class="text-slate-900">{{ money(picked.kt) }}</b> · {{ num(picked.quantity) }} pcs</span>
          <span>KH quý <b class="text-slate-900">{{ money(picked.plan_total) }}</b></span>
          <span>KH lũy kế <b class="text-slate-900">{{ money(picked.plan) }}</b></span>
          <b :style="{ color: gapColor(picked.kt_gap) }">{{ pct(picked.kt_pct, 1) }}</b>
        </div>
        <div class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Theo tháng</div>
        <el-table :data="rows" :row-class-name="rowClass" size="small" class="w-full">
          <el-table-column prop="label" label="" width="90"><template #default="{ row }"><b>{{ row.label }}</b></template></el-table-column>
          <el-table-column label="Kế hoạch" align="right"><template #default="{ row }"><span class="num">{{ dash(row.plan) }}</span></template></el-table-column>
          <el-table-column label="KH LK" align="right"><template #default="{ row }"><span class="num text-slate-500">{{ dash(row.plan_to_date) }}</span></template></el-table-column>
          <el-table-column v-if="hasKt" label="Thực đạt (KT)" align="right">
            <template #default="{ row }"><span class="num font-semibold">{{ dash(row.kt) }}</span></template>
          </el-table-column>
          <el-table-column v-if="hasKt" label="% HT" align="right" width="80">
            <template #default="{ row }"><span class="num text-slate-500">{{ pct(row.ktPct, 1) }}</span></template>
          </el-table-column>
          <el-table-column v-if="hasCf" label="PL2 CF" align="right">
            <template #default="{ row }"><span class="num" :style="{ color: cfColor(row.cf) }">{{ dash(row.cf) }}</span></template>
          </el-table-column>
          <el-table-column v-if="hasCf" label="% HT (CF)" align="right" width="90">
            <template #default="{ row }"><span class="num text-slate-500">{{ pct(row.cfPct, 1) }}</span></template>
          </el-table-column>
          <el-table-column v-if="hasKt" label="KT − KH LK" align="right">
            <template #default="{ row }">
              <span class="num" :style="{ color: gapColor(row.kt == null || row.plan_to_date == null ? null : row.kt - row.plan_to_date) }">
                {{ row.kt == null || row.plan_to_date == null ? '—' : signedMoney(row.kt - row.plan_to_date) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <template v-if="productRows.length && hasKt">
          <div class="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Theo product <span class="font-normal normal-case tracking-normal text-slate-400">· số KT: sales (pcs) và PL2 theo KT</span>
          </div>
          <el-table :data="productRows" :row-class-name="productRowClass" size="small" class="w-full" border>
            <el-table-column prop="name" label="Product" min-width="170"><template #default="{ row }"><b>{{ row.name }}</b></template></el-table-column>
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
          Kế hoạch = PL2 của tháng trong sheet kế hoạch seller; KH LK = kế hoạch đến hết khoảng ngày đang chọn (tháng lẻ theo ngày). Thực đạt = PL2 KT
          của các ngày trong khoảng; tháng ngoài khoảng ngày không có số (—). PL2 CF là số tài chính ghi theo tháng, tính trọn các tháng mà khoảng ngày chạm tới.
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
:deep(th.mh-0) { color: #1d4ed8 !important; background: #eaf1ff !important; }
:deep(th.mh-1) { color: #15803d !important; background: #e8f8ee !important; }
:deep(th.mh-2) { color: #c2410c !important; background: #fff4e5 !important; }
:deep(th.mh-total) { color: #0f172a !important; background: #eef1f6 !important; }
.seller-card__rows dd { color: var(--el-text-color-regular); font-weight: 600; font-variant-numeric: tabular-nums; }
:deep(.month-0 td:first-child) { border-left: 4px solid #2563eb; }
:deep(.month-1 td:first-child) { border-left: 4px solid #16a34a; }
:deep(.month-2 td:first-child) { border-left: 4px solid #ea580c; }
:deep(.month-total td) { background: #f6f8fb !important; font-weight: 600; }
</style>
