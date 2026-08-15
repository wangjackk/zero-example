"""粒子系统 ---- 纯逻辑层,不碰 Qt 绘制.

- ``Particle``:单个桃心粒子的状态(位置/速度/生命/色相/尺寸)
- ``ParticleSystem``:按时间步长 spawn + update,上游负责把它们画出来
"""

import math
import random
from dataclasses import dataclass


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    scale: float
    hue: float
    age: float = 0.0

    def step(self, dt: float, gravity: float) -> None:
        self.age += dt
        self.vy += gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

    def alive(self) -> bool:
        return self.age < self.life

    def frac(self) -> float:
        """剩余生命比例 0~1,1=刚出生,0=即将消亡."""
        return max(0.0, 1.0 - self.age / self.life) if self.life > 0 else 0.0


class ParticleSystem:
    def __init__(self, spawn_rate: float = 55.0, gravity: float = 90.0):
        self.particles: list[Particle] = []
        self.spawn_rate = spawn_rate
        self.gravity = gravity
        self._spawn_acc = 0.0

    def update(self, dt: float, origin: tuple[float, float]) -> None:
        self._spawn_acc += dt * self.spawn_rate
        while self._spawn_acc >= 1.0:
            self._spawn_acc -= 1.0
            self._spawn(*origin)

        for p in self.particles:
            p.step(dt, self.gravity)
        self.particles = [p for p in self.particles if p.alive()]

    def _spawn(self, cx: float, cy: float) -> None:
        ang = random.uniform(-math.pi * 0.92, -math.pi * 0.08)
        speed = random.uniform(70, 150)
        self.particles.append(Particle(
            x=cx + random.uniform(-18, 18),
            y=cy + random.uniform(-10, 10),
            vx=math.cos(ang) * speed,
            vy=math.sin(ang) * speed,
            life=random.uniform(0.9, 1.7),
            scale=random.uniform(0.25, 0.55),
            hue=random.uniform(320, 360),
        ))
