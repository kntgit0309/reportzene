<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Highcharts from 'highcharts'
import type { OrnamentGroup, OrnamentMetric } from '../../lib/types'

const props = defineProps<{ groups: OrnamentGroup[]; metric: OrnamentMetric }>()
const el = ref<HTMLDivElement | null>(null)
let chart: Highcharts.Chart | null = null

/** One stacked column per day, one colour per product type, the day's total over each column. */
function options(): Highcharts.Options {
  const isMoney = props.metric === 'total_revenue'
  const prefix = isMoney ? '$' : ''
  const days = [...new Set(props.groups.flatMap((g) => g.daily.map((d) => d.date_at)))].sort()
  return {
    credits: { enabled: false },
    title: { text: undefined },
    chart: { type: 'column', backgroundColor: 'transparent', height: 340, style: { fontFamily: 'inherit' } },
    xAxis: { categories: days, crosshair: true },
    yAxis: {
      title: { text: undefined }, reversedStacks: false,
      stackLabels: { enabled: true, format: `${prefix}{total:,.0f}`, style: { fontSize: '11px', fontWeight: '600' } },
    },
    tooltip: {
      shared: true, valueDecimals: isMoney ? 2 : 0, valuePrefix: prefix,
      footerFormat: `Total: <b>${prefix}{point.total:,.${isMoney ? 2 : 0}f}</b>`,
    },
    plotOptions: { column: { stacking: 'normal', borderRadius: 2 } },
    series: props.groups.map((g) => {
      const byDay = new Map(g.daily.map((d) => [d.date_at, Number(d[props.metric] ?? 0)]))
      return { type: 'column' as const, name: g.name, data: days.map((d) => byDay.get(d) ?? 0) }
    }),
  }
}

function draw() {
  if (!el.value) return
  if (chart) chart.destroy()
  chart = Highcharts.chart(el.value, options())
}
onMounted(draw)
watch(() => [props.groups, props.metric], draw, { deep: true })
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div ref="el" />
</template>
