<template>
  <div class="game-container">
    <div class="header">
      <span class="title">🚀 AI 太空战</span>
      <span class="level-name" v-if="levelConfig">{{ levelConfig.name }}</span>
    </div>

    <div class="status-bar" v-if="gameState === 'playing'">
      <span>Lv{{ levelConfig?.level }}</span>
      <span>Score: {{ score }}</span>
      <span>Enemies: {{ enemiesLeft }}</span>
      <span>HP: {{ hp }}</span>
    </div>

    <div v-if="gameState === 'loading'" class="loading">
      <div class="loading-text">📡 联系 AI 中...</div>
    </div>

    <div v-if="gameState === 'briefing'" class="briefing" @click="startLevel">
      <div class="briefing-card">
        <div class="mode-badge" v-if="levelConfig?.mode && levelConfig.mode !== 'shoot'">
          {{ modeLabel(levelConfig.mode) }}
        </div>
        <h2>{{ levelConfig?.name }}</h2>
        <p class="desc">{{ levelConfig?.desc }}</p>
        <div class="enemy-list" v-if="levelConfig">
          <div v-for="(e, i) in levelConfig.enemies" :key="i" class="enemy-tag">
            <span class="dot" :style="{ background: e.color || typeColor(e.type) }"></span>
            {{ e.type }} ×{{ e.count }} (HP{{e.hp}}) {{ e.shoot ? '🔫' : '' }}
          </div>
          <div v-if="levelConfig.boss" class="boss-tag">
            👹 {{ levelConfig.boss.name }} HP{{ levelConfig.boss.hp }} {{ levelConfig.boss.shoot_pattern }}
          </div>
        </div>
        <div class="ai-msg" v-if="aiMessages.length">
          <div v-for="(m, i) in aiMessages.slice(-3)" :key="i" class="ai-msg-item">🤖 {{ m }}</div>
        </div>
        <button class="start-btn">点击开始 ▶</button>
      </div>
    </div>

    <div style="display:flex;gap:12px;" v-if="gameState === 'playing'">
      <canvas ref="canvasRef" class="game-canvas"></canvas>
      <div class="ai-panel">
        <div class="ai-panel-title">🤖 AI 实时消息</div>
        <div v-for="(m, i) in aiMessages.slice(-6)" :key="i" class="ai-msg-item">{{ m }}</div>
        <div v-if="aiMessages.length === 0" class="ai-empty">等待中...</div>
      </div>
    </div>

    <div v-if="gameState === 'result'" class="result" @click="nextLevel">
      <div class="result-card" :class="{ win: lastResult?.result === 'win' }">
        <h2>{{ lastResult?.result === 'win' ? '🎉 胜利!' : '💥 失败...' }}</h2>
        <div class="result-stats" v-if="lastResult">
          <div>击杀: {{ lastResult.enemies_killed }}</div>
          <div>得分: {{ lastResult.score }}</div>
          <div>存活: {{ (lastResult.time_survived / 1000).toFixed(1) }}s</div>
        </div>
        <div class="ai-msg" v-if="aiMessages.length">
          <div v-for="(m, i) in aiMessages.slice(-3)" :key="i" class="ai-msg-item">🤖 {{ m }}</div>
        </div>
        <p class="ai-thinking" v-if="waiting">🤖 AI 正在分析并生成下一关...</p>
        <button v-else class="start-btn">下一关 ▶</button>
      </div>
    </div>

    <div class="controls" v-if="gameState === 'playing'">WASD/方向键 移动 · 自动射击</div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { GameEngine } from './engine'
import type { LevelConfig, LevelReport } from './types'

const canvasRef = ref<HTMLCanvasElement>()
const gameState = ref<'loading' | 'briefing' | 'playing' | 'result'>('loading')
const levelConfig = ref<LevelConfig | null>(null)
const lastResult = ref<LevelReport | null>(null)
const waiting = ref(false)
const score = ref(0)
const enemiesLeft = ref(0)
const hp = ref(3)
const aiMessages = ref<string[]>([])
let engine: GameEngine | null = null
let ws: WebSocket | null = null

const typeColor = (t: string): string => ({
  grunt: '#ff6b6b', fast: '#f7df1e', tank: '#e74c3c',
  shooter: '#a855f7', zigzag: '#00ff88',
})[t] || '#ff6b6b'

const modeLabel = (m: string): string => ({
  shoot: '🔫 射击模式',
  dodge: '🏃 躲避模式 (不射击,存活计时)',
  collect: '⭐ 收集模式 (收集星星,躲炸弹)',
  protect: '🛡️ 防守模式 (阻止敌人穿过)',
})[m] || '🔫 射击模式'

function connectWS() {
  ws = new WebSocket('ws://127.0.0.1:9101/ws')
  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data)
    if (data.type === 'message') {
      aiMessages.value.push(data.data)
    } else if (data.type === 'level_ready') {
      // AI 生成了新关卡，拉取并解锁"下一关"按钮
      fetch('/api/level').then(r => r.json()).then(lv => {
        levelConfig.value = lv
        waiting.value = false
      })
    } else if (data.type === 'connected') {
      aiMessages.value.push(data.data)
    }
  }
  ws.onclose = () => { setTimeout(connectWS, 2000) }
}

async function fetchLevel() {
  gameState.value = 'loading'
  try {
    const res = await fetch('/api/level')
    levelConfig.value = await res.json()
    gameState.value = 'briefing'
  } catch (e) {
    console.error('fetch level failed', e)
    setTimeout(fetchLevel, 1000)
  }
}

async function startLevel() {
  if (!levelConfig.value) return
  gameState.value = 'playing'
  await nextTick()
  if (!canvasRef.value) return
  engine = new GameEngine(canvasRef.value)
  engine.onLevelUpdate = (info) => {
    score.value = info.score
    enemiesLeft.value = info.enemies_left
    hp.value = info.hp
  }
  engine.onGameOver = (report: LevelReport) => {
    lastResult.value = report
    gameState.value = 'result'
    waiting.value = true
    const resultText = report.result === 'win' ? '胜利' : '失败'
    const msg = `[game] 第${report.level}关${resultText}! 得分:${report.score} 击杀:${report.enemies_killed} 存活:${(report.time_survived/1000).toFixed(1)}s 剩余HP:${report.player_hp}`
    fetch('http://127.0.0.1:7780/agents/world/run/send_message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: 'prime_5', message: msg }),
    }).then(() => { console.log('notified agent') })
    engine?.stop()
  }
  engine.loadLevel(levelConfig.value)
  engine.start()
}

function nextLevel() {
  if (waiting.value) return
  fetchLevel()
}

onMounted(() => {
  connectWS()
  fetchLevel()
})

onUnmounted(() => {
  engine?.destroy()
  ws?.close()
})
</script>

<style scoped>
.game-container {
  display: flex; flex-direction: column; align-items: center;
  min-height: 100vh; background: #0a0e27; color: #fff;
  font-family: 'Segoe UI', monospace;
}
.header { display: flex; gap: 20px; align-items: center; padding: 12px 0; font-size: 16px; }
.title { font-weight: bold; background: linear-gradient(90deg,#00d2ff,#a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.level-name { color: #8b9fd4; }
.status-bar { display: flex; gap: 30px; padding: 8px 0; font-size: 14px; color: #00d2ff; }
.loading { display: flex; align-items: center; justify-content: center; height: 400px; color: #4fc3f7; }
.loading-text { animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 0.5 } 50% { opacity: 1 } }
.briefing, .result { display: flex; align-items: center; justify-content: center; min-height: 400px; cursor: pointer; }
.briefing-card, .result-card {
  background: #141b3d; border: 1px solid #1e2a5a; border-radius: 12px;
  padding: 32px 40px; text-align: center; max-width: 450px;
}
.briefing-card h2 { color: #00d2ff; margin: 0 0 12px; }
.desc { color: #8b9fd4; margin: 0 0 20px; line-height: 1.6; }
.enemy-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; text-align: left; }
.enemy-tag { font-size: 13px; color: #c0c8e0; display: flex; align-items: center; gap: 8px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.boss-tag { color: #ff6b6b; font-weight: bold; margin-top: 8px; }
.ai-msg { margin: 16px 0; text-align: left; }
.ai-msg-item { font-size: 13px; color: #4fc3f7; margin: 4px 0; line-height: 1.5; }
.start-btn {
  background: linear-gradient(90deg,#00d2ff,#a855f7); border: none;
  color: #fff; padding: 12px 32px; border-radius: 8px;
  font-size: 16px; cursor: pointer; transition: transform 0.2s; margin-top: 8px;
}
.start-btn:hover { transform: scale(1.05); }
.game-canvas { border: 1px solid #1e2a5a; border-radius: 8px; box-shadow: 0 0 40px rgba(0,210,255,0.15); }
.ai-panel {
  width: 200px; background: #141b3d; border: 1px solid #1e2a5a; border-radius: 8px;
  padding: 12px; display: flex; flex-direction: column; gap: 4px; height: 640px; overflow-y: auto;
}
.ai-panel-title { color: #4fc3f7; font-size: 14px; font-weight: bold; margin-bottom: 8px; }
.ai-empty { color: #555; font-size: 12px; }
.result-card.win h2 { color: #00ff88; }
.result-card h2 { color: #ff6b6b; margin: 0 0 16px; }
.result-stats { display: flex; gap: 20px; justify-content: center; margin-bottom: 16px; color: #8b9fd4; }
.ai-thinking { color: #4fc3f7; animation: pulse 1.5s ease-in-out infinite; }
.controls { padding: 8px; font-size: 12px; color: #555; }
.mode-badge { display: inline-block; background: linear-gradient(90deg,#a855f7,#ff6b6b); color: #fff; padding: 4px 12px; border-radius: 16px; font-size: 13px; font-weight: bold; margin-bottom: 8px; }
</style>
