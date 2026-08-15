<template>
  <div class="rf-form">
    <div class="am-advanced-toggle" @click="showAdvanced = !showAdvanced">
      {{ showAdvanced ? '▾' : '▸' }} 可选参数
    </div>
    <div v-if="showAdvanced" class="am-advanced">
      <div class="am-field">
        <label class="am-label">model <span v-if="form.model" class="rf-model-clear" @click="form.model = null">×</span></label>
        <div class="rf-model-picker">
          <div class="rf-model-provs">
            <div
              v-for="p in providers"
              :key="p"
              class="rf-model-prov"
              :class="{ on: selectedProvider === p }"
              @click="selectedProvider = p"
            >{{ p }}</div>
          </div>
          <div class="rf-model-list">
            <div
              v-for="m in modelsForProvider(selectedProvider)"
              :key="m.value"
              class="rf-model-item"
              :class="{ on: form.model === m.value }"
              @click="form.model = m.value"
            >{{ m.short }}</div>
            <div v-if="!modelsForProvider(selectedProvider).length" class="rf-model-empty">—</div>
          </div>
        </div>
      </div>
    </div>

    <NButton
      class="am-create"
      size="small"
      type="primary"
      :loading="creating"
      @click="onCreate"
    >
      Create
    </NButton>
    <div v-if="createError" class="am-error">{{ createError }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { NButton } from 'naive-ui'
import type { CreateAgentParams } from '../composables/useAgents'

const props = defineProps<{
  httpBase: string
  createAgent: (params: CreateAgentParams) => Promise<string | null>
  creating: boolean
}>()

const emit = defineEmits<{
  (e: 'create', params: CreateAgentParams, newAgentId: string): void
  (e: 'error', msg: string): void
}>()

const showAdvanced = ref(false)
const createError = ref('')

const form = reactive({
  model: null as string | null,
})

// model 选项: 从 /models 拉, 按 provider 分组
interface ModelOption { label: string; value: string; short: string; provider: string }
const allModels = ref<ModelOption[]>([])
const selectedProvider = ref('')

const providers = computed<string[]>(() => {
  const set = new Set<string>()
  for (const m of allModels.value) set.add(m.provider)
  return [...set].sort()
})

function modelsForProvider(p: string): ModelOption[] {
  if (!p) return []
  return allModels.value.filter(m => m.provider === p)
}

async function loadModels() {
  try {
    const res = await fetch(`${props.httpBase}/models`)
    if (!res.ok) return
    const data = await res.json()
    const models = (data.models || []) as Array<{
      key: string; provider: string; name: string
    }>
    allModels.value = models.map(m => ({
      label: `${m.key}  (${m.name})`,
      value: m.key,
      short: m.name,
      provider: m.provider,
    }))
    if (providers.value.length && !selectedProvider.value) {
      selectedProvider.value = providers.value[0]
    }
  } catch {
    allModels.value = []
  }
}

onMounted(loadModels)

async function onCreate() {
  createError.value = ''
  try {
    const params: CreateAgentParams = {
      kind: 'react',
      model: form.model || undefined,
    }
    const id = await props.createAgent(params)
    if (id) {
      emit('create', params, id)
      form.model = null
      showAdvanced.value = false
    }
  } catch (e) {
    createError.value = (e as Error).message
    emit('error', (e as Error).message)
  }
}
</script>

<style scoped>
.rf-form {
  display: flex; flex-direction: column; gap: 8px;
  max-width: 480px;
}
.am-field { display: flex; flex-direction: column; gap: 3px; }
.am-label { font-size: 11px; color: #818cf8; }
.am-advanced-toggle {
  font-size: 11px; color: #6b7280; cursor: pointer; user-select: none;
}
.am-advanced { display: flex; flex-direction: column; gap: 8px; padding: 4px 0; }
.am-create { align-self: flex-start; }
.am-error { font-size: 11px; color: #f87171; }

.rf-model-clear {
  cursor: pointer; color: #6b7280; margin-left: 4px;
}
.rf-model-clear:hover { color: #f87171; }
.rf-model-picker {
  display: flex; gap: 6px; border: 1px solid #1f2937; border-radius: 4px; overflow: hidden;
}
.rf-model-provs {
  display: flex; flex-direction: column; border-right: 1px solid #1f2937;
  min-width: 80px; max-width: 120px;
}
.rf-model-prov {
  padding: 4px 8px; font-size: 11px; cursor: pointer; color: #9ca3af;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rf-model-prov:hover { background: #1f2937; }
.rf-model-prov.on { background: #312e81; color: #c7d2fe; }
.rf-model-list {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 6px; flex: 1;
}
.rf-model-item {
  padding: 3px 8px; font-size: 11px; cursor: pointer; border-radius: 3px;
  background: #1f2937; color: #9ca3af;
}
.rf-model-item:hover { background: #374151; color: #d1d5db; }
.rf-model-item.on { background: #4f46e5; color: #fff; }
.rf-model-empty { font-size: 11px; color: #4b5563; padding: 4px; }
</style>
