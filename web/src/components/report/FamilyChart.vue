<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Highcharts from 'highcharts'
import type { FamilyDay, FamilyGroup, FamilyMetric } from '../../lib/types'

const props = defineProps<{ groups: FamilyGroup[]; metric: FamilyMetric }>()
const el = ref<HTMLDivElement | null>(null)
let chart: Highcharts.Chart | null = null

/** The stacked lines: the product types, or the sub product types of a family with a single product type (Shirt). */
function lines(): { name: string; daily: FamilyDay[] }[] {
  const [only] = props.groups
  return props.groups.length === 1 && only.children.every((c) => c.daily) ? only.children.map((c) => ({ name: c.name, daily: c.daily ?? [] })) : props.groups
}

/** One stacked column per day, one colour per stacked line, the day's total over each column. */
function options(): Highcharts.Options {
  const isMoney = props.metric === 'total_revenue'
  const prefix = isMoney ? '$' : ''
  const stacked = lines()
  const days = [...new Set(stacked.flatMap((g) => g.daily.map((d) => d.date_at)))].sort()
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
    series: stacked.map((g) => {
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
