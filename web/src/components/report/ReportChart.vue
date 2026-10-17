<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Highcharts from 'highcharts'
import { rowLabel } from '../../lib/report'
import type { ReportRow, View } from '../../lib/types'

const TOP_SLICES = 10
const props = defineProps<{ rows: ReportRow[]; view: View; metric: 'total_revenue' | 'total_order' | 'total_quantity' }>()
const el = ref<HTMLDivElement | null>(null)
let chart: Highcharts.Chart | null = null

const value = (r: ReportRow) => Number(r[props.metric] ?? 0)
const metricName = () => ({ total_revenue: 'Revenue', total_order: 'Orders', total_quantity: 'Quantity' })[props.metric]

function options(): Highcharts.Options {
  const base: Highcharts.Options = { credits: { enabled: false }, title: { text: undefined }, chart: { backgroundColor: 'transparent', height: 320, style: { fontFamily: 'inherit' } } }
  if (props.view === 'date') {
    const rows = [...props.rows].sort((a, b) => String(a.date_at).localeCompare(String(b.date_at)))
    return { ...base, chart: { ...base.chart, type: 'areaspline' }, legend: { enabled: false },
      xAxis: { categories: rows.map((r) => r.date_at ?? ''), crosshair: true },
      yAxis: { title: { text: undefined } },
      plotOptions: { areaspline: { fillOpacity: 0.12, marker: { radius: 3 } } },
      tooltip: { valueDecimals: props.metric === 'total_revenue' ? 2 : 0, valuePrefix: props.metric === 'total_revenue' ? '$' : '' },
      series: [{ type: 'areaspline', name: metricName(), color: '#2563eb', data: rows.map(value) }] }
  }
  const sorted = [...props.rows].sort((a, b) => value(b) - value(a))
  const top = sorted.slice(0, TOP_SLICES).map((r) => ({ name: rowLabel(r, props.view), y: value(r) }))
  const rest = sorted.slice(TOP_SLICES).reduce((s, r) => s + value(r), 0)
  if (rest > 0) top.push({ name: 'Others (this page)', y: rest })
  return { ...base, chart: { ...base.chart, type: 'pie' },
    tooltip: { pointFormat: '{series.name}: <b>{point.y:,.2f}</b> ({point.percentage:.1f}%)' },
    plotOptions: { pie: { innerSize: '55%', dataLabels: { enabled: true, format: '{point.name}: {point.percentage:.1f}%', style: { fontSize: '11px', fontWeight: '500' } } } },
    series: [{ type: 'pie', name: metricName(), data: top }] }
}

function draw() {
  if (!el.value) return
  if (chart) chart.destroy()
  chart = Highcharts.chart(el.value, options())
}
onMounted(draw)
watch(() => [props.rows, props.view, props.metric], draw, { deep: true })
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div ref="el" />
</template>
