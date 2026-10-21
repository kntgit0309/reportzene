<script setup lang="ts">
import { computed } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { money, num, pct } from '../../lib/format'
import { bar, barColor, gapClass, gapOf, pcs, perDay, perDayValue, rangeDays, signedPcs } from '../../lib/plan'
import type { Family } from '../../lib/families'
import { downloadCsv } from '../../lib/report'
import type { FamilyAccountLine, FamilyAccountsReport } from '../../lib/types'

type Row = FamilyAccountLine & {
  key: string; label: string; team?: string | null; in_plan?: boolean; replaces?: string[]; gap?: number; children?: Row[]
}

const props = defineProps<{
  family: Family; report: FamilyAccountsReport | null; loading: boolean; error: string; dateFrom: string; dateTo: string
}>()

const hasPlan = computed(() => !!props.report && !props.report.plan.error)
const days = computed(() => rangeDays(props.dateFrom, props.dateTo)) // Avg sales/day
const rows = computed<Row[]>(() => (props.report?.accounts ?? []).map((a) => ({
  ...a, key: a.shop, label: a.shop, gap: gapOf(a),
  children: a.children.map((c) => ({ ...c, key: `${a.shop}/${c.name}`, label: c.name ?? '', gap: gapOf(c) })),
})))

const rowClass = ({ row }: { row: Row }) => (row.children ? 'row-parent' : 'row-child')
function footer(): string[] {
  const t = props.report?.total
  if (!t) return []
  const planCells = hasPlan.value ? [perDay(t.plan, days.value), pcs(t.plan), signedPcs(gapOf(t)), pct(t.achieved, 0), pcs(t.plan_month)] : []
  return ['All accounts', '', num(t.total_order), num(t.total_quantity), perDay(t.total_quantity, days.value), ...planCells, money(t.total_revenue), money(t.avg_order_value)]
}

function exportCsv() {
  const header = ['Account', 'Team', props.family.accountParts, 'In plan', 'Total order', 'Quantity', 'Avg sales/day', 'KH avg/day', 'Plan to date', 'Gap', '% of plan',
    'Month plan',
    'Revenue', 'Avg order value']
  const body = rows.value.flatMap((a) => [a, ...(a.children ?? [])].map((r) => [
    a.label, a.team ?? '', r === a ? '' : r.label, a.in_plan ? 'yes' : 'no', r.total_order, r.total_quantity,
    perDayValue(r.total_quantity, days.value), perDayValue(r.plan, days.value), r.plan ?? '',
    r.gap == null ? '' : Math.round(r.gap), r.achieved ?? '', r.plan_month ?? '', r.total_revenue, r.avg_order_value,
  ]))
  downloadCsv(`${props.family.key}-accounts-${props.dateFrom}_${props.dateTo}.csv`, header, body)
  ElMessage.success(`Exported ${body.length} rows`)
}
</script>

<template>
  <div class="section-card">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h3 class="card-title !mb-0">{{ family.name }} by account (store)</h3>
      <el-button size="small" type="success" plain :icon="Download" :disabled="!rows.length" @click="exportCsv">Export</el-button>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!mb-3" />
    <el-alert v-else-if="report && !hasPlan" type="info" :title="report.plan.error" :closable="false" show-icon class="!mb-3" />

    <el-table v-loading="loading" :data="rows" row-key="key" :tree-props="{ children: 'children' }" :row-class-name="rowClass"
              show-summary :summary-method="footer" :empty-text="`No sales of ${family.plural} for these filters`" class="w-full">
      <el-table-column :label="`Account / ${family.accountParts}`" min-width="230" class-name="tree-cell">
        <template #default="{ row }">
          {{ row.label }}
          <el-tag v-if="hasPlan && row.in_plan === false" size="small" type="info" class="ml-1">not in plan</el-tag>
          <div v-if="row.replaces?.length" class="truncate text-xs text-amber-600"
               :title="`Takes over the plan line and the sales of suspended ${row.replaces.join(', ')} (Settings › Plan)`">
            replaces {{ row.replaces.join(', ') }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Team" prop="team" width="90" sortable>
        <template #default="{ row }"><span class="text-muted">{{ row.team ?? '' }}</span></template>
      </el-table-column>
      <el-table-column label="Total order" prop="total_order" width="110" align="right" sortable>
        <template #default="{ row }"><span class="num">{{ num(row.total_order) }}</span></template>
      </el-table-column>
      <el-table-column label="Quantity" prop="total_quantity" width="105" align="right" sortable>
        <template #default="{ row }"><span class="num">{{ num(row.total_quantity) }}</span></template>
      </el-table-column>
      <el-table-column label="Avg sales/day" prop="total_quantity" width="110" align="right">
        <template #default="{ row }"><span class="num">{{ perDay(row.total_quantity, days) }}</span></template>
      </el-table-column>
      <template v-if="hasPlan">
        <el-table-column label="KH avg/day" prop="plan" width="95" align="right">
          <template #default="{ row }"><span class="num text-muted" title="Plan to date ÷ the days">{{ row.plan == null ? '' : perDay(row.plan, days) }}</span></template>
        </el-table-column>
        <el-table-column label="Plan to date" prop="plan" width="115" align="right" sortable>
          <template #default="{ row }"><span class="num">{{ row.plan == null ? '' : pcs(row.plan) }}</span></template>
        </el-table-column>
        <el-table-column label="Gap" prop="gap" width="100" align="right" sortable>
          <template #default="{ row }">
            <span class="num font-semibold" :class="gapClass(row.gap)" title="Quantity − Plan to date">{{ signedPcs(row.gap) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="% of plan" prop="achieved" width="150" sortable>
          <template #default="{ row }">
            <div v-if="row.plan" class="flex items-center gap-2">
              <el-progress :percentage="bar(row.achieved)" :color="barColor(row.achieved)" :show-text="false" :stroke-width="6" class="flex-1" />
              <span class="num w-11 text-right text-xs font-semibold" :style="{ color: barColor(row.achieved) }">{{ pct(row.achieved, 0) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Month plan" prop="plan_month" width="110" align="right">
          <template #default="{ row }"><span class="num text-muted">{{ row.plan_month == null ? '' : pcs(row.plan_month) }}</span></template>
        </el-table-column>
      </template>
      <el-table-column label="Revenue" prop="total_revenue" width="130" align="right" sortable>
        <template #default="{ row }"><span class="num font-semibold text-slate-900">{{ money(row.total_revenue) }}</span></template>
      </el-table-column>
      <el-table-column label="Avg order value" prop="avg_order_value" width="130" align="right">
        <template #default="{ row }"><span class="num">{{ money(row.avg_order_value) }}</span></template>
      </el-table-column>
    </el-table>
    <div class="mt-2 text-xs text-muted">
      Plan: each store's row of the plan sheet, matched by store name; {{ family.accountsNote }} A suspended store listed in
      Settings › Plan hands its plan line and its sales to its replacement.
    </div>
  </div>
</template>
