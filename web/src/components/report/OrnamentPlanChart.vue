<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Highcharts from 'highcharts'
import { pct } from '../../lib/format'
import type { OrnamentGroup } from '../../lib/types'

const props = defineProps<{ groups: OrnamentGroup[] }>()
const el = ref<HTMLDivElement | null>(null)
let chart: Highcharts.Chart | null = null

/** Per product type: pieces sold next to the plan for the same days, the % of plan over the actual column. */
function options(): Highcharts.Options {
  return {
    credits: { enabled: false },
    title: { text: undefined },
    chart: { type: 'column', backgroundColor: 'transparent', height: 320, style: { fontFamily: 'inherit' } },
    xAxis: { categories: props.groups.map((g) => g.name), crosshair: true },
    yAxis: { title: { text: 'Pieces' } },
    tooltip: { shared: true, valueDecimals: 0 },
    plotOptions: { column: { borderRadius: 3, groupPadding: 0.12 } },
    series: [
      { type: 'column', name: 'Plan to date', color: '#cbd5e1', data: props.groups.map((g) => g.plan ?? 0) },
      {
        type: 'column', name: 'Actual', color: '#2563eb',
        data: props.groups.map((g) => ({ y: g.total_quantity, custom: { label: g.achieved == null ? '' : pct(g.achieved, 0) } })),
        dataLabels: { enabled: true, format: '{point.custom.label}', style: { fontSize: '11px', fontWeight: '600' } },
      },
    ],
  }
}

function draw() {
  if (!el.value) return
  if (chart) chart.destroy()
  chart = Highcharts.chart(el.value, options())
}
onMounted(draw)
watch(() => props.groups, draw, { deep: true })
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div ref="el" />
</template>
