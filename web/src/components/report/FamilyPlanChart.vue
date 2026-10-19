<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Highcharts from 'highcharts'
import { pct } from '../../lib/format'
// A product type of a family page, or a product of Etsy › Report's overview
type Line = { name: string; total_quantity: number; plan?: number | null; achieved?: number | null }

const props = defineProps<{ groups: Line[] }>()
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
    plotOptions: { column: { borderRadius: 3, groupPadding: 0.12, maxPointWidth: 120 } }, // Shirt's single pair stays column-sized
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
