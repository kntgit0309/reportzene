<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import ReportChart from './ReportChart.vue'
import ReportTable from './ReportTable.vue'
import { DEFAULT_SORT, fetchReport, VIEWS } from '../../lib/report'
import type { ReportPage, ReportRow, View } from '../../lib/types'

// The report's views (Date, Order, Product, Store, Seller, Product type) with chart, table and paging, for the applied
// filters in `params`. A new params object (an Apply or Refresh in the page) reloads from the first page.
const PAGE_SIZES = [20, 50, 100, 200]
const props = withDefaults(defineProps<{ params: Record<string, string>; initialView?: View; title?: string }>(),
  { initialView: 'date', title: '' })
const emit = defineEmits<{ loaded: [page: ReportPage]; viewChange: [view: View] }>()

const view = ref<View>(props.initialView)
const table = reactive({ page: 1, perPage: 50, sortBy: DEFAULT_SORT[props.initialView], sortOrder: 'desc' })
const rows = ref<ReportRow[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const showChart = ref(true)
const metric = ref<'total_revenue' | 'total_order' | 'total_quantity'>('total_revenue')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const page = await fetchReport({ ...props.params, view: view.value, page: table.page, per_page: table.perPage,
      sort_by: table.sortBy || DEFAULT_SORT[view.value], sort_order: table.sortOrder || 'desc' })
    rows.value = page.rows
    total.value = page.paging.total
    emit('loaded', page)
  } catch (e) {
    rows.value = []
    total.value = 0
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
function changeView(v: View) {
  view.value = v
  table.page = 1
  table.sortBy = DEFAULT_SORT[v]
  table.sortOrder = 'desc'
  emit('viewChange', v)
  load()
}
function onSort(by: string, order: string) {
  table.sortBy = by || DEFAULT_SORT[view.value]
  table.sortOrder = order || 'desc'
  table.page = 1
  load()
}
const chartable = computed(() => view.value !== 'order' && view.value !== 'product' && rows.value.length > 0)

watch(() => props.params, () => {
  table.page = 1
  load()
})
onMounted(load)
defineExpose({ reload: load })
</script>

<template>
  <div class="section-card">
    <h3 v-if="title" class="card-title">{{ title }}</h3>
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <el-segmented :model-value="view" :options="VIEWS" class="segmented-tabs" @change="(v: View) => changeView(v)" />
      <div class="flex items-center gap-3">
        <el-select v-if="chartable && showChart" v-model="metric" size="small" class="!w-[130px]">
          <el-option label="Revenue" value="total_revenue" />
          <el-option label="Orders" value="total_order" />
          <el-option label="Quantity" value="total_quantity" />
        </el-select>
        <el-switch v-if="chartable" v-model="showChart" active-text="Chart" />
      </div>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!mb-3" />
    <ReportChart v-if="chartable && showChart" :rows="rows" :view="view" :metric="metric" class="mb-3" />

    <ReportTable :rows="rows" :view="view" :loading="loading" :params="params" :sort-by="table.sortBy" :sort-order="table.sortOrder" @sort="onSort" />

    <div class="mt-3 flex justify-end">
      <el-pagination v-model:current-page="table.page" v-model:page-size="table.perPage" :page-sizes="PAGE_SIZES" :total="total" background
                     layout="total, sizes, prev, pager, next" @current-change="load" @size-change="table.page = 1; load()" />
    </div>
    <slot />
  </div>
</template>
