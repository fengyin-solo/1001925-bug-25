<template>
  <section class="page" data-module="forecast">
    <header class="page-head">
      <div>
        <h2>功率预测管理</h2>
        <p class="page-desc">维护功率预测单，围绕预测单号、所属场站、预测日期、预测出力做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记功率预测单</button>
        <button class="btn" type="button" :disabled="exporting" @click="exportRows">
          {{ exporting ? '导出中…' : '导出功率预测清单' }}
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无功率预测数据，可先登记功率预测单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条功率预测记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/forecast'
const columns = ["预测单号", "所属场站", "预测日期", "预测出力", "实际出力", "预测偏差", "考核电量", "预测状态"]
const actions = ["生成预测", "登记偏差超标", "复核预测"]
const statuses = ["待生成", "已生成", "偏差超标", "已复核"]
const stats = [{"label": "待生成预测", "value": 0}, {"label": "偏差超标天数", "value": 0}, {"label": "预测准确率", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const exporting = ref(false)
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

// 列表筛选项与后端查询参数的对应关系，列表与导出共用，保证两边是同一批数据。
const QUERY_KEYS: Record<string, string> = {
  预测单号: 'keyword',
  所属场站: 'station',
  预测日期: 'forecast_date',
}

function buildQuery() {
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (filters.value[field] ?? '').trim()
    if (value) {
      params.append(QUERY_KEYS[field], value)
    }
  }
  return params.toString()
}

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  // 失败时不清空筛选条件，用户可直接重试；导出成功也不刷新列表，记录保持原样。
  errorMessage.value = ''
  exporting.value = true
  try {
    const query = buildQuery()
    const response = await request(`${ENDPOINT}/export${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error('功率预测清单导出失败，请稍后重试')
    }
    const payload = await response.json()
    downloadExport(payload.items ?? [])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '功率预测清单导出失败'
  } finally {
    exporting.value = false
  }
}

function downloadExport(items: Row[]) {
  const header = columns
  const lines = [header.join(',')]
  for (const item of items) {
    lines.push(header.map((column) => csvCell(item[column])).join(','))
  }
  // 加 BOM，避免 Excel 打开中文列名乱码。
  const blob = new Blob([`﻿${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `功率预测清单_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function csvCell(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') {
    return ''
  }
  const text = String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function openCreate() {
  errorMessage.value = '功率预测单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('功率预测动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '功率预测操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = buildQuery()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error('功率预测单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '功率预测列表读取失败'
  }
}

onMounted(reload)
</script>
