<template>
  <div class="xml-runner">
    <!-- 顶部工具栏 -->
    <div class="xr-header">
      <span class="xr-title">XML Runner</span>
      <div class="xr-actions">
        <NButton size="small" quaternary @click="clear">⌫ 清空</NButton>
        <NButton
          size="small"
          type="primary"
          :loading="running"
          :disabled="!canRun"
          @click="run"
        >
          {{ running ? '执行中' : '▶ 运行' }}
        </NButton>
      </div>
    </div>

    <div class="xr-layout">
      <!-- 左侧:列表 + 文档 -->
      <div class="xr-left">
        <!-- routine 列表 -->
        <div class="xr-sidebar">
          <div class="xr-filter-row">
            <NInput
              v-model:value="filter"
              size="small"
              placeholder="搜索..."
              clearable
              class="xr-search"
            />
            <NSelect
              v-model:value="hubFilter"
              size="small"
              :options="hubOptions"
              class="xr-hub-select"
            />
          </div>
          <div class="xr-list">
          <NScrollbar style="height:100%">
            <div
              v-for="r in filteredRoutines"
              :key="r.name"
              class="xr-routine"
              :class="{ hidden: r.meta?.hidden, passive: r.is_passive, active: selected?.name === r.name }"
              @click="selectRoutine(r)"
            >
              <span class="xr-routine-name">{{ r.name }}</span>
              <NTag v-if="r.meta?.hidden" size="tiny" :bordered="false" style="color:#6b7280">hidden</NTag>
              <NTag v-if="r.is_passive" size="tiny" type="info" :bordered="false">passive</NTag>
            </div>
            <div v-if="!filteredRoutines.length" class="xr-empty">无结果</div>
          </NScrollbar>
          </div>
        </div>

        <!-- 文档面板:仅 XML tab 显示(表单 tab 自带介绍,冗余) -->
        <div v-if="selected && activeTab === 'xml'" class="xr-doc">
        <NScrollbar style="height:100%">
          <div class="xr-doc-inner">
            <div class="xr-doc-name">{{ selected.name }}</div>
            <div class="xr-doc-tags">
              <NTag v-if="selected.is_passive" size="small" type="info" :bordered="false">passive</NTag>
              <NTag v-if="selected.meta?.hidden" size="small" :bordered="false" style="color:#6b7280">hidden</NTag>
            </div>
            <p v-if="selected.meta?.description || selected.doc" class="xr-doc-desc">{{ selected.meta?.description || selected.doc }}</p>
            <div v-if="paramsList.length" class="xr-params">
              <div class="xr-params-title">参数</div>
              <div v-for="p in paramsList" :key="p.name" class="xr-param">
                <div class="xr-param-head">
                  <span class="xr-param-name">{{ p.name }}</span>
                  <span class="xr-param-type">{{ p.type }}</span>
                  <span class="xr-param-flag" :class="p.required ? 'is-required' : 'is-optional'">{{ p.required ? '必填' : '可选' }}</span>
                </div>
                <div v-if="p.description" class="xr-param-desc">{{ p.description }}</div>
                <div v-if="p.default !== undefined" class="xr-param-default">默认 <code>{{ p.default }}</code></div>
              </div>
            </div>
            <pre class="xr-doc-example">{{ buildXmlTag(selected) }}</pre>
            <NButton size="small" quaternary @click="insertTag(selected)">↙ 插入编辑框</NButton>
          </div>
        </NScrollbar>
        </div>
      </div>

      <!-- 右侧:表单/XML 编辑 + 结果 -->
      <div class="xr-body">
        <NTabs v-model:value="activeTab" type="line" size="small" class="xr-tabs" pane-style="height:100%;display:flex;flex-direction:column;">
          <NTabPane name="form" tab="表单" class="xr-pane">
            <div v-if="!selected" class="xr-form-empty">请从左侧选择一个 routine</div>
            <NScrollbar v-else style="height:100%">
              <div class="xr-form">
                <div class="xr-form-name">{{ selected.name }}</div>
                <p v-if="selected.meta?.description" class="xr-form-desc">{{ selected.meta?.description }}</p>
                <div v-if="selected.is_passive" class="xr-form-noparams xr-form-readonly">passive routine 由系统自动拉起,不可手动运行</div>
                <div v-else-if="!paramsList.length" class="xr-form-noparams">该 routine 无参数,直接点运行</div>
                <div v-for="p in paramsList" :key="p.name" class="xr-form-field">
                  <div class="xr-form-head">
                    <span class="xr-form-label">{{ p.name }}</span>
                    <span class="xr-form-type">{{ p.type }}</span>
                    <span class="xr-form-flag" :class="p.required ? 'is-required' : 'is-optional'">{{ p.required ? '必填' : '可选' }}</span>
                  </div>
                  <div class="xr-form-input">
                    <NInputNumber
                      v-if="p.type === 'number' || p.type === 'integer'"
                      v-model:value="formValues[p.name]"
                      size="small"
                      style="width:100%"
                    />
                    <NSwitch
                      v-else-if="p.type === 'boolean'"
                      v-model:value="formValues[p.name]"
                      size="small"
                    />
                    <NInput
                      v-else
                      v-model:value="formValues[p.name]"
                      size="small"
                      :placeholder="p.default ? `默认 ${p.default}` : ''"
                    />
                  </div>
                  <div v-if="p.description" class="xr-form-hint">{{ p.description }}</div>
                </div>
              </div>
            </NScrollbar>
          </NTabPane>
          <NTabPane name="xml" tab="XML" class="xr-pane">
            <NInput
              ref="editorRef"
              v-model:value="xml"
              type="textarea"
              placeholder='<query_weather city="北京"/>'
              :autosize="false"
              class="xr-editor"
              @keydown.ctrl.enter.prevent="run"
              @keydown.meta.enter.prevent="run"
            />
          </NTabPane>
        </NTabs>

        <template v-if="results.length || error">
          <NAlert v-if="error" type="error" :show-icon="false" class="xr-error">
            <pre>{{ error }}</pre>
          </NAlert>
          <div class="xr-results">
          <NScrollbar style="height:100%">
            <div v-for="(r, i) in results" :key="i" class="xr-result-item">
              <span class="xr-result-name">{{ r.name }}</span>
              <pre class="xr-result-value">{{ formatResult(r.result) }}</pre>
            </div>
          </NScrollbar>
          </div>
        </template>
        <div v-else-if="!running" class="xr-hint">{{ activeTab === 'form' ? '填好参数点运行' : 'Ctrl+Enter 运行' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { NInput, NInputNumber, NSwitch, NButton, NTag, NSelect, NTabs, NTabPane, NScrollbar, NAlert } from 'naive-ui'

interface JsonSchemaProperty {
  type?: string
  description?: string
  default?: unknown
  title?: string
  [key: string]: unknown
}

interface JsonSchema {
  type?: string
  title?: string
  description?: string
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
  [key: string]: unknown
}

export interface RoutineMeta {
  description?: string
  input_schema?: JsonSchema
  output_schema?: JsonSchema
  hidden?: boolean
  tool?: boolean
  [key: string]: unknown
}

export interface RoutineInfo {
  name: string
  is_passive?: boolean
  hub_id?: string
  meta?: RoutineMeta
}

interface RunResult {
  name: string
  result: unknown
}

const props = defineProps<{
  routines: RoutineInfo[]
}>()

interface RunPayload {
  format: 'form' | 'xml'
  name?: string
  kwargs?: Record<string, unknown>
  xml?: string
}

const emit = defineEmits<{
  run: [payload: RunPayload, onResult: (data: unknown[]) => void, onError: (msg: string) => void, onDone: () => void]
}>()

const xml = ref('')
const filter = ref('')
const hubFilter = ref<string>('')
const activeTab = ref<'form' | 'xml'>('form')
const formValues = ref<Record<string, unknown>>({})
const selected = ref<RoutineInfo | null>(null)
const running = ref(false)
const results = ref<RunResult[]>([])
const error = ref('')
const editorRef = ref<InstanceType<typeof NInput> | null>(null)

// 选中 routine 变化时,用 input_schema 默认值初始化表单(类型安全:number→null,
// boolean→false,其余→'' ).无 schema 的 routine 表单空着,靠 paramsList 兜底为空.
watch(selected, (r) => {
  formValues.value = {}
  if (!r?.meta?.input_schema?.properties) return
  for (const [name, prop] of Object.entries(r.meta.input_schema.properties)) {
    const t = prop.type
    if (t === 'number' || t === 'integer') {
      formValues.value[name] = prop.default !== undefined ? Number(prop.default) : null
    } else if (t === 'boolean') {
      formValues.value[name] = prop.default !== undefined ? Boolean(prop.default) : false
    } else {
      formValues.value[name] = prop.default !== undefined ? String(prop.default) : ''
    }
  }
})

const filteredRoutines = computed(() => {
  const q = filter.value.toLowerCase()
  const hub = hubFilter.value
  return props.routines.filter(r => {
    if (hub && (r.hub_id || '') !== hub) return false
    if (!q) return true
    return r.name.includes(q)
      || r.doc?.toLowerCase().includes(q)
      || r.meta?.description?.toLowerCase().includes(q)
  })
})

const hubOptions = computed(() => {
  const hubs = new Set<string>()
  for (const r of props.routines) {
    if (r.hub_id) hubs.add(r.hub_id)
  }
  return [
    { label: '全部 hub', value: '' },
    ...[...hubs].sort().map(h => ({ label: h, value: h })),
  ]
})

interface ParamItem {
  name: string
  type: string
  description: string
  default?: string
  required: boolean
}

function parseParamDoc(doc: string): ParamItem[] {
  if (!doc) return []
  const items: ParamItem[] = []
  for (const line of doc.split('\n')) {
    const m = line.match(/^\s*-\s*(\S+):\s*(\S+)(?:\s+(.*))?$/)
    if (!m) continue
    const [, name, type, rest = ''] = m
    let description = rest
    let defaultValue: string | undefined
    let required = true
    const defaultMatch = description.match(/\(default=(.+?)\)/)
    if (defaultMatch) {
      defaultValue = defaultMatch[1]
      description = description.replace(defaultMatch[0], '').trim()
    }
    if (description.includes('(optional)')) {
      required = false
      description = description.replace('(optional)', '').trim()
    }
    items.push({ name, type, description, default: defaultValue, required })
  }
  return items
}

const paramsList = computed<ParamItem[]>(() => {
  const r = selected.value
  if (!r) return []
  if (r.meta?.input_schema?.properties) {
    const required = new Set(r.meta.input_schema.required ?? [])
    return Object.entries(r.meta.input_schema.properties).map(([name, prop]) => ({
      name,
      type: prop.type ?? 'any',
      description: prop.description ?? '',
      default: prop.default !== undefined ? JSON.stringify(prop.default) : undefined,
      required: required.has(name),
    }))
  }
  return parseParamDoc(r.param_doc ?? '')
})

function selectRoutine(r: RoutineInfo): void {
  selected.value = selected.value?.name === r.name ? null : r
}

/** 按逗号分割参数,忽略括号/方括号内部的逗号(如 dict[str, Any]) */
function splitParams(s: string): string[] {
  const parts: string[] = []
  let depth = 0
  let cur = ''
  for (const ch of s) {
    if (ch === '[' || ch === '(') depth++
    else if (ch === ']' || ch === ')') depth--
    if (ch === ',' && depth === 0) { parts.push(cur); cur = '' }
    else cur += ch
  }
  if (cur) parts.push(cur)
  return parts
}

function buildXmlTag(r: RoutineInfo): string {
  if (r.meta?.input_schema?.properties) {
    const parts = Object.entries(r.meta.input_schema.properties).map(([name, prop]) => {
      const val = prop.default !== undefined ? String(prop.default) : ''
      return `${name}="${val}"`
    })
    return parts.length ? `<${r.name} ${parts.join(' ')}/>` : `<${r.name}/>`
  }
  return buildXmlTagFromSignature(r)
}

function buildXmlTagFromSignature(r: RoutineInfo): string {
  const sig = r.signature ?? ''
  // 提取最外层括号内容,使用深度计数而非简单正则,避免嵌套括号截断
  let inner = ''
  let depth = 0
  let started = false
  for (const ch of sig) {
    if (ch === '(' && !started) { started = true; depth = 1; continue }
    if (!started) continue
    if (ch === '(') depth++
    else if (ch === ')') { depth--; if (depth === 0) break }
    inner += ch
  }
  const paramParts = splitParams(inner)
    .map(s => s.trim())
    .filter(s => s && s !== 'self' && !s.startsWith('*'))
    .map(s => {
      const name = s.split(':')[0].split('=')[0].trim()
      const defaultMatch = s.match(/=\s*(.+)$/)
      const val = defaultMatch ? defaultMatch[1].trim().replace(/^['"]|['"]$/g, '') : ''
      return name ? `${name}="${val}"` : null
    })
    .filter((x): x is string => Boolean(x))
  return paramParts.length ? `<${r.name} ${paramParts.join(' ')}/>` : `<${r.name}/>`
}

function insertTag(r: RoutineInfo): void {
  const tag = buildXmlTag(r)
  xml.value = xml.value ? xml.value + '\n' + tag : tag
  activeTab.value = 'xml'
  editorRef.value?.focus()
}

const canRun = computed(() => {
  if (running.value) return false
  // passive routine 由 kernel 自动拉起,不允许手动运行(可选中查看文档,但 Run 禁用)
  if (selected.value?.is_passive) return false
  if (activeTab.value === 'form') return !!selected.value
  return !!xml.value.trim()
})

function clear(): void {
  xml.value = ''
  results.value = []
  error.value = ''
  editorRef.value?.focus()
}

function formatResult(val: unknown): string {
  if (typeof val === 'object' && val !== null) return JSON.stringify(val, null, 2)
  return String(val ?? '')
}

async function run(): Promise<void> {
  if (running.value || !canRun.value) return
  running.value = true
  error.value = ''
  results.value = []
  if (activeTab.value === 'form') {
    // 表单路径:直接调 routine,跳过 XML 解析
    const r = selected.value
    if (!r) { running.value = false; return }
    const payload: RunPayload = {
      format: 'form',
      name: r.name,
      kwargs: { ...formValues.value },
    }
    emit('run', payload, onResult, onError, onDone)
  } else {
    // XML 路径:走 run_xml 编排(支持多标签 + DAG)
    const xmlStr = xml.value.trim()
    if (!xmlStr) { running.value = false; return }
    const payload: RunPayload = { format: 'xml', xml: xmlStr }
    emit('run', payload, onResult, onError, onDone)
  }
}

function onResult(data: unknown[]): void {
  results.value = Array.isArray(data)
    ? (data as RunResult[])
    : [{ name: 'result', result: data }]
}

function onError(msg: string): void {
  error.value = msg
}

function onDone(): void {
  running.value = false
}

defineExpose({ onResult, onError, onDone })
</script>

<style scoped>
.xml-runner {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #13151f;
}

.xr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid #2d3148;
  flex-shrink: 0;
}

.xr-title {
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.xr-actions { display: flex; gap: 6px; }

.xr-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 左侧 */
.xr-left {
  flex: 2;
  min-width: 0;
  display: flex;
  overflow: hidden;
  border-right: 1px solid #2d3148;
}

.xr-sidebar {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #2d3148;
  overflow: hidden;
}

.xr-filter-row { display: flex; gap: 0; border-bottom: 1px solid #2d3148; }
.xr-search { flex: 1; border-radius: 0 !important; border: none; }
.xr-hub-select { width: 96px; flex-shrink: 0; }
.xr-hub-select :deep(.n-base-selection) { border-radius: 0 !important; border: none; border-left: 1px solid #2d3148; }

.xr-list { flex: 1; overflow: hidden; }

.xr-routine {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  cursor: pointer;
  font-size: 14px;
  color: #cbd5e1;
  transition: background 0.1s;
  user-select: none;
}
.xr-routine:hover { background: #1e2235; color: #fff; }
.xr-routine.active { background: #252a40; color: #a5b4fc; }
.xr-routine.hidden { color: #6b7280; }
.xr-routine.hidden:hover { color: #94a3b8; }
.xr-routine.passive { color: #6b7280; }
.xr-routine.passive:hover { color: #94a3b8; }

.xr-routine-name {
  flex: 1;
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.xr-empty { font-size: 13px; color: #4b5280; text-align: center; padding: 14px; }

/* 文档面板 */
.xr-doc {
  flex: 1.2;
  min-width: 0;
  overflow: hidden;
  background: #0f1117;
}

.xr-doc-inner {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

.xr-doc-name {
  font-weight: 700;
  color: #c7d2fe;
  font-family: monospace;
  font-size: 15px;
}

.xr-doc-tags { display: flex; gap: 4px; flex-wrap: wrap; }

.xr-doc-desc {
  color: #cbd5e1;
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}

.xr-params {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.xr-params-title {
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.6px;
}

.xr-param {
  background: #1a1d27;
  border: 1px solid #2d3148;
  border-radius: 4px;
  padding: 6px 8px;
}

.xr-param-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.xr-param-name {
  font-family: monospace;
  font-size: 12px;
  color: #c7d2fe;
  font-weight: 600;
}

.xr-param-type {
  font-family: monospace;
  font-size: 11px;
  color: #818cf8;
  background: rgba(129, 140, 248, 0.1);
  padding: 1px 5px;
  border-radius: 3px;
}

.xr-param-flag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 500;
}

.xr-param-flag.is-required {
  color: #fca5a5;
  background: rgba(252, 165, 165, 0.08);
}

.xr-param-flag.is-optional {
  color: #6b7280;
  background: rgba(107, 114, 128, 0.1);
}

.xr-param-desc {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
  margin-top: 4px;
}

.xr-param-default {
  font-size: 11px;
  color: #6b7280;
  margin-top: 3px;
}

.xr-param-default code {
  font-family: monospace;
  color: #a5b4fc;
}

.xr-doc-example {
  background: #131720;
  border: 1px solid #22c55e33;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 15px;
  color: #86efac;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

/* 右侧编辑区 */
.xr-body {
  display: flex;
  flex-direction: column;
  flex: 3;
  min-width: 0;
  overflow: hidden;
  padding: 10px;
  gap: 8px;
}

.xr-tabs { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.xr-tabs :deep(.n-tabs-pane) { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.xr-pane { height: 100%; display: flex; flex-direction: column; overflow: hidden; }

.xr-form-empty { margin: auto; color: #4b5280; font-size: 13px; text-align: center; }

.xr-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 4px 20px;
}

.xr-form-name {
  font-family: monospace;
  font-size: 16px;
  font-weight: 700;
  color: #c7d2fe;
}

.xr-form-desc { margin: -4px 0 4px; font-size: 12px; color: #94a3b8; line-height: 1.5; }

.xr-form-noparams { color: #6b7280; font-size: 13px; padding: 8px 0; }
.xr-form-readonly { color: #fca5a5; }

.xr-form-field {
  background: #1a1d27;
  border: 1px solid #2d3148;
  border-radius: 5px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.xr-form-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.xr-form-label { font-family: monospace; font-size: 12px; color: #c7d2fe; font-weight: 600; }
.xr-form-type { font-family: monospace; font-size: 11px; color: #818cf8; background: rgba(129,140,248,0.1); padding: 1px 5px; border-radius: 3px; }
.xr-form-flag { font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: 500; }
.xr-form-flag.is-required { color: #fca5a5; background: rgba(252,165,165,0.08); }
.xr-form-flag.is-optional { color: #6b7280; background: rgba(107,114,128,0.1); }
.xr-form-hint { font-size: 11px; color: #6b7280; line-height: 1.5; }

.xr-editor {
  flex: 1;
  font-family: 'Consolas', 'Fira Code', monospace !important;
  font-size: 14px !important;
}

/* 让 NInput textarea 撑满高度 */
.xr-editor :deep(.n-input__textarea-el) {
  height: 100%;
  resize: none;
  font-family: inherit;
  font-size: inherit;
  color: #c7d2fe;
  line-height: 1.6;
}

.xr-error {
  flex-shrink: 0;
}
.xr-error pre {
  margin: 0;
  font-family: monospace;
  font-size: 13px;
  white-space: pre-wrap;
}

.xr-results { flex-shrink: 0; max-height: 40%; overflow: hidden; }

.xr-result-item {
  background: #131720;
  border: 1px solid #2d3148;
  border-left: 3px solid #22c55e;
  border-radius: 5px;
  padding: 8px 12px;
  margin-bottom: 6px;
}

.xr-result-name {
  display: block;
  font-size: 13px;
  color: #86efac;
  font-weight: 600;
  margin-bottom: 5px;
  font-family: monospace;
}

.xr-result-value {
  font-size: 13px;
  color: #cbd5e1;
  font-family: 'Consolas', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.xr-hint {
  font-size: 13px;
  color: #4b5280;
  text-align: center;
  padding: 4px;
}
</style>
