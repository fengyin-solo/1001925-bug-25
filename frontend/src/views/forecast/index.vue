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
          {{ exporting ? '正在导出…' : '导出功率预测清单' }}
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
      <label class="filter-item">
        <span>预测单号</span>
        <input v-model="filters.keyword" placeholder="按预测单号检索" />
      </label>
      <label class="filter-item">
        <span>所属场站</span>
        <input v-model="filters.station" placeholder="按所属场站检索" />
      </label>
      <label class="filter-item">
        <span>预测日期起</span>
        <input v-model="filters.start_date" type="date" />
      </label>
      <label class="filter-item">
        <span>预测日期止</span>
        <input v-model="filters.end_date" type="date" />
      </label>
      <label class="filter-item">
        <span>预测状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
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
      <span v-if="noticeMessage" class="success-text">{{ noticeMessage }}</span>
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
const noticeMessage = ref('')
const exporting = ref(false)
const filters = ref<Record<string, string>>({
  keyword: '',
  station: '',
  start_date: '',
  end_date: '',
  status: '',
})

// 列表查询与导出共用同一份条件拼参，保证两边取数口径一致。
function buildQuery() {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    const trimmed = value.trim()
    if (trimmed) {
      params.set(key, trimmed)
    }
  }
  return params.toString()
}

function resetFilters() {
  for (const key of Object.keys(filters.value)) {
    filters.value[key] = ''
  }
  void reload()
}

async function exportRows() {
  if (exporting.value) {
    return
  }
  // 导出失败时不清空任何已选条件，用户可直接重试。
  exporting.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const query = buildQuery()
    const response = await request(`${ENDPOINT}/export${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error(`导出请求返回 ${response.status}，已保留当前条件，请重试`)
    }
    const payload = (await response.json()) as { total?: number; items?: Row[]; fields?: string[] }
    downloadCsv(payload)
    noticeMessage.value = `已导出 ${payload.total ?? payload.items?.length ?? 0} 条待处理预测偏差，列表数据未改动`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '功率预测清单导出失败，请重试'
  } finally {
    exporting.value = false
  }
}

function downloadCsv(payload: { items?: Row[]; fields?: string[] }) {
  const fields = payload.fields ?? columns
  const items = payload.items ?? []
  const escapeCell = (value: unknown) => {
    const text = value === null || value === undefined ? '' : String(value)
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const lines = [
    fields.map(escapeCell).join(','),
    ...items.map((row) => fields.map((field) => escapeCell(row[field] ?? '')).join(',')),
  ]
  // ﻿ 便于 Excel 直接按 UTF-8 打开，中文不乱码。
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `功率预测偏差清单_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function openCreate() {
  errorMessage.value = '功率预测单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
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
  noticeMessage.value = ''
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
