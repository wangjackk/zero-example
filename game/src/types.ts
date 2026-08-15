// 游戏类型定义

export type GameMode = 'shoot' | 'dodge' | 'collect' | 'protect'

export interface EnemyConfig {
  type: string
  count: number
  speed: number
  hp: number
  shoot: boolean
  shoot_interval?: number
  color?: string
  size?: number
  pattern?: string
}

export interface BossConfig {
  name: string
  hp: number
  speed: number
  shoot: boolean
  shoot_interval: number
  shoot_pattern: string
  color: string
  size: number
}

export interface CollectibleConfig {
  type: string        // star / bomb / heal
  count: number
  speed: number
  good: boolean      // true=收集加分, false=碰到扣血
  color: string
  size?: number
}

export interface LevelConfig {
  level: number
  name: string
  desc: string
  mode?: GameMode       // 游戏模式: shoot(默认) / dodge / collect / protect
  enemies: EnemyConfig[]
  spawn_interval: number
  boss: BossConfig | null
  bg_color?: string
  star_speed?: number
  survival_time?: number  // dodge/protect 模式: 存活多少ms算赢
  collectibles?: CollectibleConfig[]  // collect 模式的掉落物
  collect_target?: number  // collect 模式: 目标分数
  protect_zone?: { x: number; y: number; r: number }  // protect 模式: 保护区域
}

export interface LevelReport {
  level: number
  result: 'win' | 'lose'
  score: number
  enemies_killed: number
  time_survived: number
  player_hp: number
  mode?: string
  collect_score?: number
}
