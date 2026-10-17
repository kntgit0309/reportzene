<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const props = defineProps<{ title?: string; subtitle?: string }>()
const route = useRoute()
const heading = computed(() => props.title ?? route.meta.title ?? '')
</script>

<template>
  <div class="page-header">
    <div class="page-header__left">
      <el-breadcrumb v-if="route.meta.group" separator="/" class="text-xs">
        <el-breadcrumb-item>{{ route.meta.group }}</el-breadcrumb-item>
        <el-breadcrumb-item>{{ heading }}</el-breadcrumb-item>
      </el-breadcrumb>
      <h1 class="page-header__title">{{ heading }}</h1>
      <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
    </div>
    <div class="page-header__right"><slot name="actions" /></div>
  </div>
</template>
