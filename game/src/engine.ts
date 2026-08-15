// 游戏引擎: 4 种模式 (shoot / dodge / collect / protect)
import type { LevelConfig, LevelReport, EnemyConfig, CollectibleConfig } from './types'

interface Entity {
  x: number; y: number; vx: number; vy: number
  w: number; h: number; hp: number; maxHp: number
  color: string; type: string; shoot: boolean
  shootInterval?: number; shootTimer?: number
  pattern?: string; t?: number; baseX?: number; hitFlash?: number
}

interface Bullet {
  x: number; y: number; vx: number; vy: number
  w: number; h: number; color: string; fromPlayer: boolean; damage: number
}

interface Particle {
  x: number; y: number; vx: number; vy: number
  life: number; maxLife: number; color: string; size: number
}

interface Star { x: number; y: number; speed: number; size: number; brightness: number }

interface Collectible {
  x: number; y: number; vy: number; w: number; h: number; color: string; good: boolean; type: string
}

export class GameEngine {
  canvas: HTMLCanvasElement
  ctx: CanvasRenderingContext2D
  W = 480; H = 640

  player: Entity | null = null
  enemies: Entity[] = []
  bullets: Bullet[] = []
  particles: Particle[] = []
  stars: Star[] = []
  collectibles: Collectible[] = []

  keys: Record<string, boolean> = {}
  shootCooldown = 0
  level: LevelConfig | null = null
  mode: string = 'shoot'
  spawnQueue: Entity[] = []
  collectSpawnQueue: Collectible[] = []
  spawnTimer = 0
  collectSpawnTimer = 0
  bossSpawned = false
  enemiesKilled = 0
  score = 0
  collectScore = 0
  startTime = 0
  survivalElapsed = 0
  running = false
  gameOver = false
  won = false

  onGameOver: ((report: LevelReport) => void) | null = null
  onLevelUpdate: ((info: any) => void) | null = null

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas; this.canvas.width = this.W; this.canvas.height = this.H
    this.ctx = canvas.getContext('2d')!
    this.initStars(); this.bindKeys()
  }

  initStars() {
    this.stars = []
    for (let i = 0; i < 100; i++) this.stars.push({
      x: Math.random()*this.W, y: Math.random()*this.H,
      speed: 0.5+Math.random()*2, size: Math.random()*2+0.5, brightness: 0.3+Math.random()*0.7,
    })
  }

  bindKeys() {
    window.addEventListener('keydown', (e) => { this.keys[e.key.toLowerCase()] = true; if (e.key===' ') e.preventDefault() })
    window.addEventListener('keyup', (e) => { this.keys[e.key.toLowerCase()] = false })
  }

  loadLevel(config: LevelConfig) {
    this.level = config
    this.mode = config.mode || 'shoot'
    this.enemies = []; this.bullets = []; this.particles = []; this.collectibles = []
    this.spawnQueue = []; this.collectSpawnQueue = []; this.spawnTimer = 0; this.collectSpawnTimer = 0
    this.bossSpawned = false; this.enemiesKilled = 0; this.score = 0; this.collectScore = 0
    this.startTime = Date.now(); this.survivalElapsed = 0
    this.gameOver = false; this.won = false

    this.player = { x: this.W/2, y: this.H-60, vx:0, vy:0, w:30, h:30, hp:3, maxHp:3, color:'#00d2ff', type:'player', shoot:false }

    for (const ec of config.enemies || []) for (let i = 0; i < ec.count; i++) this.spawnQueue.push(this.makeEnemy(ec))

    // collect 模式: 准备掉落物
    if (this.mode === 'collect' && config.collectibles) {
      for (const cc of config.collectibles) for (let i = 0; i < cc.count; i++) {
        this.collectSpawnQueue.push({ x: 30+Math.random()*(this.W-60), y: -20-Math.random()*500,
          vy: cc.speed, w: cc.size||20, h: cc.size||20, color: cc.color, good: cc.good, type: cc.type })
      }
    }
    this.running = true
  }

  makeEnemy(ec: EnemyConfig): Entity {
    const size = ec.size || 24
    return { x:30+Math.random()*(this.W-60), y:-size-Math.random()*200, vx:0, vy:ec.speed*0.8,
      w:size, h:size, hp:ec.hp, maxHp:ec.hp, color: ec.color||'#ff6b6b', type:ec.type, shoot:ec.shoot,
      shootInterval: ec.shoot_interval||2000, shootTimer: Math.random()*1500,
      pattern: ec.pattern||'straight', t:0, baseX:0, hitFlash:0 }
  }

  spawnBoss() {
    if (!this.level?.boss || this.bossSpawned) return
    this.bossSpawned = true
    const b = this.level.boss
    this.enemies.push({ x:this.W/2, y:-50, vx:0, vy:b.speed*0.5, w:b.size, h:b.size,
      hp:b.hp, maxHp:b.hp, color:b.color, type:'boss', shoot:b.shoot,
      shootInterval:b.shoot_interval, shootTimer:0, pattern:'boss', t:0, baseX:this.W/2, hitFlash:0 })
  }

  update(dt: number) {
    if (!this.running || this.gameOver) return
    const dts = dt / 16.67
    const p = this.player!
    const starSpd = this.level?.star_speed || 1
    for (const s of this.stars) { s.y += s.speed*starSpd*dts; if (s.y>this.H){s.y=0;s.x=Math.random()*this.W} }

    // 玩家移动 (所有模式通用)
    const sp = 5
    if (this.keys['arrowleft']||this.keys['a']) p.x -= sp*dts
    if (this.keys['arrowright']||this.keys['d']) p.x += sp*dts
    if (this.keys['arrowup']||this.keys['w']) p.y -= sp*dts
    if (this.keys['arrowdown']||this.keys['s']) p.y += sp*dts
    p.x = Math.max(p.w/2, Math.min(this.W-p.w/2, p.x))
    p.y = Math.max(p.h/2, Math.min(this.H-p.h/2, p.y))

    // === shoot 模式: 自动射击 ===
    if (this.mode === 'shoot') {
      this.shootCooldown -= dt
      if (this.shootCooldown <= 0) {
        this.bullets.push({ x:p.x, y:p.y-p.h/2, vx:0, vy:-10, w:4, h:14, color:'#00d2ff', fromPlayer:true, damage:1 })
        this.shootCooldown = 180
      }
      this.updateShootMode(dt, dts, p)
    }
    // === dodge 模式: 不射击, 存活计时 ===
    else if (this.mode === 'dodge') {
      this.survivalElapsed += dt
      this.updateDodgeMode(dt, dts, p)
      if (this.survivalElapsed >= (this.level?.survival_time || 20000)) {
        this.won = true; this.endGame('win'); return
      }
    }
    // === collect 模式: 收集掉落物 ===
    else if (this.mode === 'collect') {
      this.updateCollectMode(dt, dts, p)
      if (this.collectScore >= (this.level?.collect_target || 100)) {
        this.won = true; this.endGame('win'); return
      }
    }
    // === protect 模式: 保护区域不被敌人穿过 ===
    else if (this.mode === 'protect') {
      this.shootCooldown -= dt
      if (this.shootCooldown <= 0) {
        this.bullets.push({ x:p.x, y:p.y-p.h/2, vx:0, vy:-10, w:4, h:14, color:'#00d2ff', fromPlayer:true, damage:1 })
        this.shootCooldown = 180
      }
      this.updateProtectMode(dt, dts, p)
    }

    this.updateBullets(dt, dts, p)
    this.updateParticles(dt, dts)

    this.onLevelUpdate?.({
      enemies_left: this.enemies.length + this.spawnQueue.length,
      score: this.score, hp: p.hp, level: this.level?.level||1,
      mode: this.mode,
      survival: this.survivalElapsed,
      survival_target: this.level?.survival_time,
      collect_score: this.collectScore,
      collect_target: this.level?.collect_target,
    })
  }

  // ---- shoot 模式 ----
  updateShootMode(dt: number, dts: number, p: Entity) {
    this.spawnTimer += dt
    if (this.spawnQueue.length > 0 && this.spawnTimer >= (this.level?.spawn_interval||1500)) {
      this.spawnTimer = 0; this.enemies.push(this.spawnQueue.shift()!)
    }
    if (this.spawnQueue.length===0 && this.enemies.length===0 && !this.bossSpawned && this.level?.boss) this.spawnBoss()
    if (this.spawnQueue.length===0 && this.enemies.length===0 && (!this.level?.boss || this.bossSpawned)) {
      this.won = true; this.endGame('win'); return
    }
    this.updateEnemies(dt, dts, p)
  }

  // ---- dodge 模式 ----
  updateDodgeMode(dt: number, dts: number, p: Entity) {
    // 敌人不断生成,只射击不碰撞扣血
    this.spawnTimer += dt
    if (this.spawnQueue.length > 0 && this.spawnTimer >= (this.level?.spawn_interval||1000)) {
      this.spawnTimer = 0; this.enemies.push(this.spawnQueue.shift()!)
      // 补充敌人保持压力
      if (this.spawnQueue.length < 3) {
        for (const ec of this.level?.enemies||[]) this.spawnQueue.push(this.makeEnemy(ec))
      }
    }
    this.updateEnemies(dt, dts, p)
  }

  // ---- collect 模式 ----
  updateCollectMode(dt: number, dts: number, p: Entity) {
    // 掉落物下落
    this.collectSpawnTimer += dt
    if (this.collectSpawnQueue.length > 0 && this.collectSpawnTimer >= 600) {
      this.collectSpawnTimer = 0
      const c = this.collectSpawnQueue.shift()!
      c.x = 30 + Math.random()*(this.W-60); c.y = -20
      this.collectibles.push(c)
      // 补充
      if (this.collectSpawnQueue.length < 5) {
        if (this.level?.collectibles) for (const cc of this.level.collectibles) {
          this.collectSpawnQueue.push({ x:0, y:0, vy:cc.speed, w:cc.size||20, h:cc.size||20, color:cc.color, good:cc.good, type:cc.type })
        }
      }
    }
    // 掉落物移动 + 碰撞
    for (let i = this.collectibles.length-1; i >= 0; i--) {
      const c = this.collectibles[i]
      c.y += c.vy * dts
      if (c.y > this.H + 30) { this.collectibles.splice(i, 1); continue }
      if (this.aabb(c, p)) {
        if (c.good) { this.collectScore += 10; this.explode(c.x, c.y, c.color, 8) }
        else { p.hp -= 1; this.explode(p.x, p.y, '#ff6b6b', 8); if (p.hp<=0){this.endGame('lose');return} }
        this.collectibles.splice(i, 1)
      }
    }
  }

  // ---- protect 模式 ----
  updateProtectMode(dt: number, dts: number, p: Entity) {
    this.survivalElapsed += dt
    this.spawnTimer += dt
    if (this.spawnQueue.length > 0 && this.spawnTimer >= (this.level?.spawn_interval||1200)) {
      this.spawnTimer = 0; this.enemies.push(this.spawnQueue.shift()!)
      if (this.spawnQueue.length < 3) for (const ec of this.level?.enemies||[]) this.spawnQueue.push(this.makeEnemy(ec))
    }
    this.updateEnemies(dt, dts, p)
    // 敌人穿过底部 = 失败
    for (const e of this.enemies) {
      if (e.y > this.H - 20) { this.endGame('lose'); return }
    }
    if (this.survivalElapsed >= (this.level?.survival_time || 25000)) {
      this.won = true; this.endGame('win'); return
    }
  }

  // ---- 通用: 敌人更新 ----
  updateEnemies(dt: number, dts: number, p: Entity) {
    for (let i = this.enemies.length-1; i >= 0; i--) {
      const e = this.enemies[i]
      e.t = (e.t||0) + dt
      if (e.baseX === 0) e.baseX = e.x
      switch (e.pattern) {
        case 'sine': e.y += e.vy*dts*0.6; e.x = (e.baseX||e.x) + Math.sin(e.t/400)*80; break
        case 'zigzag': e.y += e.vy*dts*0.7; e.x += Math.sin(e.t/200)*3*dts; e.x = Math.max(20,Math.min(this.W-20,e.x)); break
        case 'boss': if (e.y<80) e.y += e.vy*dts; else e.x = (e.baseX||this.W/2)+Math.sin(e.t/600)*120; break
        default: e.y += e.vy*dts
      }
      if (e.shoot) { e.shootTimer = (e.shootTimer||0)-dt; if (e.shootTimer<=0){e.shootTimer=e.shootInterval||2000; this.enemyShoot(e)} }
      e.hitFlash = Math.max(0, (e.hitFlash||0)-dt)
      if (e.y > this.H+50) this.enemies.splice(i, 1)
      if (this.aabb(e, p)) {
        p.hp -= 1; this.explode(e.x, e.y, e.color, 15); this.enemies.splice(i, 1)
        if (p.hp <= 0) { this.endGame('lose'); return }
      }
    }
  }

  enemyShoot(e: Entity) {
    if (!this.player) return
    const dx = this.player.x - e.x, dy = this.player.y - e.y
    const dist = Math.hypot(dx, dy) || 1, spd = 4
    if (e.type === 'boss' && this.level?.boss) {
      const pat = this.level.boss.shoot_pattern
      if (pat === 'spread') for (let a=-0.4;a<=0.4;a+=0.2){const ang=Math.atan2(dy,dx)+a;this.bullets.push({x:e.x,y:e.y,vx:Math.cos(ang)*spd,vy:Math.sin(ang)*spd,w:6,h:6,color:e.color,fromPlayer:false,damage:1})}
      else if (pat === 'spiral'){const ang=(e.t||0)/200;for(let k=0;k<4;k++){const a=ang+k*Math.PI/2;this.bullets.push({x:e.x,y:e.y,vx:Math.cos(a)*spd,vy:Math.sin(a)*spd,w:5,h:5,color:e.color,fromPlayer:false,damage:1})}}
      else if (pat === 'burst') for(let k=0;k<8;k++){const a=(k/8)*Math.PI*2;this.bullets.push({x:e.x,y:e.y,vx:Math.cos(a)*spd,vy:Math.sin(a)*spd,w:5,h:5,color:e.color,fromPlayer:false,damage:1})}
      else this.bullets.push({x:e.x,y:e.y,vx:(dx/dist)*spd,vy:(dy/dist)*spd,w:5,h:5,color:e.color,fromPlayer:false,damage:1})
    } else {
      this.bullets.push({x:e.x,y:e.y,vx:(dx/dist)*spd,vy:(dy/dist)*spd,w:4,h:8,color:e.color,fromPlayer:false,damage:1})
    }
  }

  updateBullets(dt: number, dts: number, p: Entity) {
    for (let i = this.bullets.length-1; i >= 0; i--) {
      const b = this.bullets[i]
      b.x += b.vx*dts; b.y += b.vy*dts
      if (b.y<-20||b.y>this.H+20||b.x<-20||b.x>this.W+20) { this.bullets.splice(i,1); continue }
      if (b.fromPlayer) {
        for (let j = this.enemies.length-1; j >= 0; j--) {
          const e = this.enemies[j]
          if (this.aabb(b, e)) {
            e.hp -= b.damage; e.hitFlash = 100; this.bullets.splice(i,1)
            if (e.hp <= 0) {
              this.score += e.type==='boss'?1000:100; this.enemiesKilled++
              this.explode(e.x, e.y, e.color, e.type==='boss'?40:12); this.enemies.splice(j,1)
            }
            break
          }
        }
      } else {
        if (this.aabb(b, p)) {
          p.hp -= 1; this.bullets.splice(i,1); this.explode(p.x, p.y, '#ff6b6b', 8)
          if (p.hp <= 0) { this.endGame('lose'); return }
        }
      }
    }
  }

  updateParticles(dt: number, dts: number) {
    for (let i = this.particles.length-1; i >= 0; i--) {
      const pa = this.particles[i]
      pa.x += pa.vx*dts; pa.y += pa.vy*dts; pa.vy += 0.1*dts; pa.life -= dt
      if (pa.life <= 0) this.particles.splice(i, 1)
    }
  }

  explode(x: number, y: number, color: string, count: number) {
    for (let i = 0; i < count; i++) {
      const a = Math.random()*Math.PI*2, s = 1+Math.random()*4
      this.particles.push({ x, y, vx:Math.cos(a)*s, vy:Math.sin(a)*s, life:400+Math.random()*300, maxLife:700, color, size:2+Math.random()*3 })
    }
  }

  aabb(a: any, b: any): boolean {
    return Math.abs(a.x-b.x) < (a.w+b.w)/2 && Math.abs(a.y-b.y) < (a.h+b.h)/2
  }

  endGame(result: 'win' | 'lose') {
    this.gameOver = true; this.running = false
    this.onGameOver?.({
      level: this.level?.level||1, result, score: this.score + this.collectScore,
      enemies_killed: this.enemiesKilled, time_survived: Date.now()-this.startTime,
      player_hp: this.player?.hp||0, mode: this.mode, collect_score: this.collectScore,
    })
  }

  render() {
    const ctx = this.ctx
    ctx.fillStyle = this.level?.bg_color || '#0a0e27'
    ctx.fillRect(0, 0, this.W, this.H)

    for (const s of this.stars) { ctx.globalAlpha = s.brightness; ctx.fillStyle = '#fff'; ctx.fillRect(s.x, s.y, s.size, s.size) }
    ctx.globalAlpha = 1

    // collect 模式: 掉落物
    for (const c of this.collectibles) {
      ctx.fillStyle = c.color; ctx.shadowColor = c.color; ctx.shadowBlur = 12
      ctx.beginPath(); ctx.arc(c.x, c.y, c.w/2, 0, Math.PI*2); ctx.fill()
      if (!c.good) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke() }
      ctx.shadowBlur = 0
    }

    for (const pa of this.particles) { ctx.globalAlpha = pa.life/pa.maxLife; ctx.fillStyle = pa.color; ctx.fillRect(pa.x-pa.size/2, pa.y-pa.size/2, pa.size, pa.size) }
    ctx.globalAlpha = 1

    for (const b of this.bullets) { ctx.fillStyle = b.color; ctx.shadowColor = b.color; ctx.shadowBlur = 8; ctx.fillRect(b.x-b.w/2, b.y-b.h/2, b.w, b.h) }
    ctx.shadowBlur = 0

    // protect 模式: 保护区域
    if (this.mode === 'protect' && this.level?.protect_zone) {
      const z = this.level.protect_zone
      ctx.strokeStyle = '#00ff88'; ctx.lineWidth = 2; ctx.globalAlpha = 0.3 + Math.sin(Date.now()/300)*0.2
      ctx.beginPath(); ctx.arc(z.x, z.y, z.r, 0, Math.PI*2); ctx.stroke()
      ctx.globalAlpha = 1
    }

    for (const e of this.enemies) {
      if (e.hitFlash && e.hitFlash > 0) { ctx.fillStyle = '#fff' }
      else { ctx.fillStyle = e.color; ctx.shadowColor = e.color; ctx.shadowBlur = 10 }
      const half = e.w/2
      if (e.type === 'boss') {
        ctx.fillRect(e.x-half, e.y-half, e.w, e.h)
        ctx.shadowBlur = 0; ctx.fillStyle = '#333'; ctx.fillRect(this.W/2-100, 10, 200, 8)
        ctx.fillStyle = '#ff6b6b'; ctx.fillRect(this.W/2-100, 10, 200*(e.hp/e.maxHp), 8)
      } else { ctx.beginPath(); ctx.arc(e.x, e.y, half, 0, Math.PI*2); ctx.fill() }
      ctx.shadowBlur = 0
    }

    if (this.player) {
      const p = this.player
      ctx.fillStyle = p.color; ctx.shadowColor = p.color; ctx.shadowBlur = 15
      ctx.beginPath(); ctx.moveTo(p.x, p.y-p.h/2); ctx.lineTo(p.x-p.w/2, p.y+p.h/2); ctx.lineTo(p.x, p.y+p.h/4); ctx.lineTo(p.x+p.w/2, p.y+p.h/2); ctx.closePath(); ctx.fill()
      ctx.shadowBlur = 0
      for (let i = 0; i < p.maxHp; i++) { ctx.fillStyle = i<p.hp?'#00d2ff':'#333'; ctx.fillRect(10+i*22, this.H-20, 16, 4) }
    }

    // dodge/protect 模式: 倒计时
    if ((this.mode === 'dodge' || this.mode === 'protect') && this.level?.survival_time) {
      const remain = Math.max(0, (this.level.survival_time - this.survivalElapsed) / 1000)
      ctx.fillStyle = '#4fc3f7'; ctx.font = 'bold 20px monospace'
      ctx.fillText(remain.toFixed(1)+'s', this.W-70, 25)
    }
    // collect 模式: 分数
    if (this.mode === 'collect' && this.level?.collect_target) {
      ctx.fillStyle = '#00ff88'; ctx.font = 'bold 16px monospace'
      ctx.fillText(`${this.collectScore}/${this.level.collect_target}`, this.W-90, 25)
    }
  }

  loop = (ts: number) => {
    if (!this._lastTs) this._lastTs = ts
    const dt = Math.min(ts - this._lastTs, 50); this._lastTs = ts
    this.update(dt); this.render()
    if (this.running) requestAnimationFrame(this.loop)
  }
  _lastTs = 0
  start() { this.running = true; this._lastTs = 0; requestAnimationFrame(this.loop) }
  stop() { this.running = false }
  destroy() { this.stop(); this.running = false }
}
