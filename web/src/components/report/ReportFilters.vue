<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowDown, ArrowUp, Refresh, Search } from '@element-plus/icons-vue'
import { fetchOptions, shortcuts, SYMBOLS } from '../../lib/report'
import type { Filters, Option } from '../../lib/types'

const filters = defineModel<Filters>({ required: true })
const teamsTouched = defineModel<boolean>('teamsTouched', { required: true })
const props = defineProps<{ defaultTeams: string[] }>()
const emit = defineEmits<{ apply: []; reset: [] }>()

const advanced = ref(false)
const opts = ref<Record<string, Option[]>>({ shops: [], sellers: [], designers: [], product_types: [], teams: [] })
const loadingOpts = ref(false)
const optionError = ref('')

onMounted(async () => {
  loadingOpts.value = true
  try {
    const kinds = Object.keys(opts.value)
    const lists = await Promise.all(kinds.map((k) => fetchOptions(k)))
    kinds.forEach((k, i) => { opts.value[k] = lists[i] })
  } catch (e) {
    optionError.value = (e as Error).message
  } finally {
    loadingOpts.value = false
  }
})

const teamOptions = computed(() => opts.value.teams.filter((t) => t.type !== 'bu'))
// Teams not touched yet: show the server default (ZenE teams from Settings) as the current value
const teamsModel = computed<number[]>({
  get: () => (teamsTouched.value ? filters.value.teams : props.defaultTeams.map(Number)),
  set: (v) => { teamsTouched.value = true; filters.value.teams = v },
})

const chips = computed(() => {
  const f = filters.value
  const name = (kind: string, id: number | string) => opts.value[kind].find((o) => String(o.id) === String(id))?.name ?? String(id)
  const out: string[] = []
  if (f.keyword) out.push(`Keyword: ${f.keyword}`)
  for (const [k, label] of [['shops', 'Store'], ['sellers', 'Seller'], ['designers', 'Designer'], ['product_types', 'Type']] as const) {
    if (f[k].length) out.push(`${label}: ${f[k].map((id) => name(k, id)).join(', ')}`)
  }
  if (teamsModel.value.length) out.push(`Team: ${teamsModel.value.map((id) => name('teams', id)).join(', ')}`)
  if (f.total_order) out.push(`Total order ${f.symbol} ${f.total_order}`)
  return out
})
</script>

<template>
  <div class="section-card">
    <el-form label-position="top" @submit.prevent="emit('apply')">
      <div class="filter-grid">
        <el-form-item label="Date">
          <el-date-picker v-model="filters.dateRange" type="daterange" value-format="YYYY-MM-DD" format="DD/MM/YYYY" :shortcuts="shortcuts()"
                          :clearable="false" unlink-panels range-separator="→" class="!w-full" />
        </el-form-item>
        <el-form-item label="Keyword">
          <el-input v-model="filters.keyword" clearable placeholder="Product name, SKU…" :prefix-icon="Search" />
        </el-form-item>
        <el-form-item label="Store">
          <el-select v-model="filters.shops" multiple filterable collapse-tags collapse-tags-tooltip :max-collapse-tags="2" placeholder="All stores" :loading="loadingOpts" class="w-full">
            <el-option v-for="o in opts.shops" :key="o.id" :label="o.name" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Seller">
          <el-select v-model="filters.sellers" multiple filterable collapse-tags collapse-tags-tooltip :max-collapse-tags="2" placeholder="All sellers" :loading="loadingOpts" class="w-full">
            <el-option v-for="o in opts.sellers" :key="o.id" :label="o.name" :value="o.id" />
          </el-select>
        </el-form-item>
      </div>

      <div v-show="advanced" class="filter-grid mt-1 border-t border-[#eef1f6] pt-4">
        <el-form-item label="Designer">
          <el-select v-model="filters.designers" multiple filterable collapse-tags collapse-tags-tooltip :max-collapse-tags="2" placeholder="All designers" class="w-full">
            <el-option v-for="o in opts.designers" :key="o.id" :label="o.name" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Product type">
          <el-select v-model="filters.product_types" multiple filterable collapse-tags collapse-tags-tooltip :max-collapse-tags="2" placeholder="All types" class="w-full">
            <el-option v-for="o in opts.product_types" :key="o.id" :label="o.name" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Team">
          <el-select v-model="teamsModel" multiple filterable collapse-tags collapse-tags-tooltip :max-collapse-tags="2" placeholder="All teams" class="w-full">
            <el-option v-for="o in teamOptions" :key="o.id" :label="o.name" :value="o.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Total order">
          <el-input v-model="filters.total_order" type="number" min="0" placeholder="Enter total order" clearable>
            <template #prepend>
              <el-select v-model="filters.symbol" class="!w-[72px]">
                <el-option v-for="s in SYMBOLS" :key="s" :label="s" :value="s" />
              </el-select>
            </template>
          </el-input>
        </el-form-item>
      </div>

      <el-alert v-if="optionError" type="warning" :closable="false" show-icon :title="`Filter lists unavailable: ${optionError}`" class="!mb-3" />

      <div class="flex flex-wrap items-center gap-2 pt-1">
        <el-tag v-for="c in chips" :key="c" type="info" effect="light" round>{{ c }}</el-tag>
        <div class="ml-auto flex gap-2">
          <el-button link type="primary" :icon="advanced ? ArrowUp : ArrowDown" @click="advanced = !advanced">{{ advanced ? 'Fewer filters' : 'More filters' }}</el-button>
          <el-button :icon="Refresh" @click="emit('reset')">Reset</el-button>
          <el-button type="primary" native-type="submit" :icon="Search">Apply</el-button>
        </div>
      </div>
    </el-form>
  </div>
</template>
