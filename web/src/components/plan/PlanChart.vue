<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Highcharts from 'highcharts'
import type { PlanLine } from '../../lib/types'

const MONTH_COLORS = ['#93c5fd', '#3b82f6', '#1e40af'] // light → dark through the quarter
const props = defineProps<{ products: PlanLine[]; months: string[]; metric: 'pl2' | 'sales' }>()
const el = ref<HTMLDivElement | null>(null)
let chart: Highcharts.Chart | null = null

function options(): Highcharts.Options {
  const isMoney = props.metric === 'pl2'
  return {
    credits: { enabled: false },
    title: { text: undefined },
    chart: { type: 'column', backgroundColor: 'transparent', height: 340, style: { fontFamily: 'inherit' } },
    xAxis: { categories: props.products.map((p) => p.product), crosshair: true },
    yAxis: { title: { text: undefined }, reversedStacks: false, stackLabels: { enabled: true, format: isMoney ? '${total:,.0f}' : '{total:,.0f}', style: { fontSize: '11px', fontWeight: '600' } } },
    tooltip: { shared: true, valueDecimals: 0, valuePrefix: isMoney ? '$' : '' },
    plotOptions: { column: { stacking: 'normal', borderRadius: 3 } },
    series: props.months.map((m, i) => ({
      type: 'column' as const, name: m, color: MONTH_COLORS[i % MONTH_COLORS.length], data: props.products.map((p) => p[props.metric][i] ?? 0),
    })),
  }
}

function draw() {
  if (!el.value) return
  if (chart) chart.destroy()
  chart = Highcharts.chart(el.value, options())
}
onMounted(draw)
watch(() => [props.products, props.months, props.metric], draw, { deep: true })
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div ref="el" />
</template>
