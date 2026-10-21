<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Highcharts from 'highcharts'
import { money, pct } from '../../lib/format'

// Etsy › Report: each item's part of a total (PL2 by product, by account), one horizontal bar each, largest first, labelled
// with its share of the total. A part can be negative (CF): its bar goes left of 0 and its share is negative.
type Item = { name: string; value: number }
const axisMoney = (v: number) => (v < 0 ? '−$' : '$') + Highcharts.numberFormat(Math.abs(v), 0, '.', ',')
const props = defineProps<{ title: string; valueLabel: string; items: Item[]; total: number | null | undefined; color: (v: number) => string }>()
const el = ref<HTMLDivElement | null>(null)
let chart: Highcharts.Chart | null = null

function options(): Highcharts.Options {
  const items = [...props.items].sort((a, b) => b.value - a.value)
  const total = props.total
  const share = (v: number) => (total && total > 0 ? pct(v / total, 1) : '') // no share of a total that is not positive
  return {
    credits: { enabled: false },
    title: { text: props.title, align: 'left', style: { fontSize: '13px', fontWeight: '600' } },
    chart: { type: 'bar', backgroundColor: 'transparent', height: Math.max(180, 70 + items.length * 26), spacingRight: 28,
             style: { fontFamily: 'inherit' } },
    legend: { enabled: false },
    xAxis: { categories: items.map((i) => i.name), lineColor: '#e2e8f0', labels: { style: { fontSize: '11px' } } },
    yAxis: {
      title: { text: undefined }, gridLineColor: '#f1f5f9',
      labels: { formatter() { return axisMoney(Number(this.value)) }, style: { fontSize: '10px', textOverflow: 'none' } },
      plotLines: [{ value: 0, color: '#94a3b8', width: 1, zIndex: 3 }],
    },
    tooltip: {
      headerFormat: '<span style="font-size:11px">{point.key}</span><br/>',
      pointFormat: `${props.valueLabel}: <b>{point.custom.amount}</b><br/>Share of the total: <b>{point.custom.share}</b>`,
    },
    plotOptions: {
      bar: {
        borderRadius: 3, pointPadding: 0.08, groupPadding: 0.04, borderWidth: 0,
        dataLabels: { enabled: true, format: '{point.custom.share}', crop: false, overflow: 'allow',
                      style: { fontSize: '11px', fontWeight: '600', color: '#334155', textOutline: 'none' } },
      },
    },
    series: [{
      type: 'bar', name: props.valueLabel,
      data: items.map((i) => ({ y: i.value, color: props.color(i.value), custom: { amount: money(i.value), share: share(i.value) } })),
    }],
  }
}

function draw() {
  if (!el.value) return
  if (chart) chart.destroy()
  chart = Highcharts.chart(el.value, options())
}
onMounted(draw)
watch(() => [props.items, props.total], draw, { deep: true })
onBeforeUnmount(() => chart?.destroy())
</script>

<template>
  <div ref="el" />
</template>
