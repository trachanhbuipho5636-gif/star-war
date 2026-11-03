"""
effects.py - Real-Time Particle VFX Engine, Atmospheric Ion Rain,
Lightning Controller, and Camera Trauma System.
"""

import math
import random
from panda3d.core import (
    NodePath,
    Vec3,
    Vec4,
    CardMaker,
    TransparencyAttrib,
    ColorBlendAttrib,
)


class Particle:
    __slots__ = ("np", "vel", "age", "lifetime", "start_scale", "end_scale", "start_color", "end_color", "drag")

    def __init__(self, np: NodePath, vel: Vec3, lifetime: float, start_scale: float, end_scale: float, start_color: Vec4, end_color: Vec4, drag: float = 1.0):
        self.np = np
        self.vel = vel
        self.age = 0.0
        self.lifetime = max(0.05, lifetime)
        self.start_scale = start_scale
        self.end_scale = end_scale
        self.start_color = start_color
        self.end_color = end_color
        self.drag = drag


class ParticleSystem:
    """High-performance pooled additive billboard particle system."""

    def __init__(self, parent_np: NodePath, particle_tex):
        self.root = parent_np.attachNewNode("ParticleSystemRoot")
        # Additive blending + depth-write disabled for glowing volumetric particles
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.root.setAttrib(
            ColorBlendAttrib.make(
                ColorBlendAttrib.MAdd,
                ColorBlendAttrib.OIncomingAlpha,
                ColorBlendAttrib.OOne,
            )
        )
        self.root.setDepthWrite(False)
        self.root.setLightOff()
        self.root.setShaderOff()

        cm = CardMaker("particle_quad")
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        self.template_np = NodePath(cm.generate())
        self.template_np.setBillboardPointEye()
        if particle_tex:
            self.template_np.setTexture(particle_tex)

        self.active_particles: list[Particle] = []
        self.pool: list[NodePath] = []
        self._preallocate_pool(220)

    def _preallocate_pool(self, count: int):
        for _ in range(count):
            p_np = self.template_np.copyTo(self.root)
            p_np.hide()
            self.pool.append(p_np)

    def _acquire_node(self) -> NodePath:
        if self.pool:
            p_np = self.pool.pop()
            p_np.show()
            return p_np
        p_np = self.template_np.copyTo(self.root)
        return p_np

    def spawn_particle(
        self,
        pos: Vec3,
        vel: Vec3,
        lifetime: float,
        start_scale: float,
        end_scale: float,
        start_color: Vec4,
        end_color: Vec4,
        drag: float = 1.2,
    ):
        if len(self.active_particles) > 420:
            return
        p_np = self._acquire_node()
        p_np.setPos(pos)
        p_np.setScale(start_scale)
        p_np.setColor(start_color)
        self.active_particles.append(
            Particle(p_np, vel, lifetime, start_scale, end_scale, start_color, end_color, drag)
        )

    def spawn_explosion(self, pos: Vec3, color_core: Vec4 = Vec4(1.0, 0.65, 0.2, 1.0), scale_mult: float = 1.0):
        # Core flash
        self.spawn_particle(
            pos,
            Vec3(0, 0, 0),
            0.35,
            3.5 * scale_mult,
            14.0 * scale_mult,
            Vec4(1.0, 0.95, 0.85, 1.0),
            Vec4(color_core.x, color_core.y, color_core.z, 0.0),
            drag=1.0,
        )
        # High-velocity sparks and plasma embers
        for _ in range(26):
            theta = random.uniform(0.0, math.pi * 2.0)
            phi = random.uniform(-math.pi * 0.45, math.pi * 0.45)
            spd = random.uniform(12.0, 42.0) * scale_mult
            vel = Vec3(
                math.cos(theta) * math.cos(phi) * spd,
                math.sin(theta) * math.cos(phi) * spd,
                math.sin(phi) * spd + 4.0,
            )
            self.spawn_particle(
                pos,
                vel,
                random.uniform(0.45, 0.95),
                random.uniform(1.2, 2.4) * scale_mult,
                0.2,
                color_core,
                Vec4(0.9, 0.15, 0.05, 0.0),
                drag=2.4,
            )

    def spawn_hit_sparks(self, pos: Vec3, color: Vec4 = Vec4(0.2, 0.9, 1.0, 1.0)):
        for _ in range(8):
            vel = Vec3(
                random.uniform(-18.0, 18.0),
                random.uniform(-18.0, 18.0),
                random.uniform(-10.0, 22.0),
            )
            self.spawn_particle(
                pos,
                vel,
                random.uniform(0.18, 0.38),
                1.1,
                0.15,
                color,
                Vec4(color.x, color.y, color.z, 0.0),
                drag=3.0,
            )

    def spawn_nova_shockwave(self, center: Vec3):
        ring_samples = 36
        for i in range(ring_samples):
            ang = (2.0 * math.pi * i) / ring_samples
            vel = Vec3(math.cos(ang) * 75.0, math.sin(ang) * 75.0, 0.0)
            self.spawn_particle(
                center,
                vel,
                0.65,
                2.8,
                6.5,
                Vec4(0.25, 0.95, 1.0, 1.0),
                Vec4(0.55, 0.15, 1.0, 0.0),
                drag=1.1,
            )

    def update(self, dt: float):
        alive = []
        for p in self.active_particles:
            p.age += dt
            if p.age >= p.lifetime:
                p.np.hide()
                self.pool.append(p.np)
                continue

            t = p.age / p.lifetime
            p.vel *= max(0.0, 1.0 - p.drag * dt)
            p.np.setPos(p.np.getPos() + p.vel * dt)

            scale = p.start_scale + (p.end_scale - p.start_scale) * t
            p.np.setScale(scale)

            col = p.start_color + (p.end_color - p.start_color) * t
            p.np.setColor(col)
            alive.append(p)

        self.active_particles = alive

    def clear_all(self):
        for p in self.active_particles:
            p.np.hide()
            self.pool.append(p.np)
        self.active_particles.clear()


class WeatherAndCameraFX:
    """Manages atmospheric ion rain streaks, storm lightning flashes, and camera shake."""

    def __init__(self, parent_np: NodePath, particle_tex):
        self.root = parent_np.attachNewNode("WeatherRoot")
        self.root.setTransparency(TransparencyAttrib.MAlpha)
        self.root.setAttrib(
            ColorBlendAttrib.make(
                ColorBlendAttrib.MAdd,
                ColorBlendAttrib.OIncomingAlpha,
                ColorBlendAttrib.OOne,
            )
        )
        self.root.setDepthWrite(False)
        self.root.setLightOff()
        self.root.setShaderOff()

        cm = CardMaker("rain_streak")
        cm.setFrame(-0.06, 0.06, -1.6, 1.6)
        template = NodePath(cm.generate())
        template.setBillboardAxis()
        if particle_tex:
            template.setTexture(particle_tex)

        self.rain_drops = []
        for _ in range(95):
            drop = template.copyTo(self.root)
            drop.setColor(0.35, 0.72, 1.0, 0.35)
            offset = Vec3(
                random.uniform(-45.0, 45.0),
                random.uniform(-45.0, 45.0),
                random.uniform(-10.0, 35.0),
            )
            self.rain_drops.append([drop, offset, random.uniform(38.0, 58.0)])

        self.lightning_intensity = 0.0
        self.lightning_timer = random.uniform(4.5, 10.0)
        self.camera_trauma = 0.0
        self.time_accum = 0.0

    def add_trauma(self, amount: float):
        self.camera_trauma = min(1.0, self.camera_trauma + amount)

    def update(self, dt: float, anchor_pos: Vec3, weather_enabled: bool):
        self.time_accum += dt
        self.camera_trauma = max(0.0, self.camera_trauma - dt * 1.8)

        if not weather_enabled:
            self.root.hide()
            self.lightning_intensity = 0.0
            return

        self.root.show()
        for item in self.rain_drops:
            drop_np, offset, speed = item
            offset.z -= speed * dt
            if offset.z < -12.0:
                offset.z = 34.0
                offset.x = random.uniform(-45.0, 45.0)
                offset.y = random.uniform(-45.0, 45.0)
            drop_np.setPos(anchor_pos + offset)

        # Periodic ion storm lightning
        self.lightning_timer -= dt
        if self.lightning_timer <= 0.0:
            self.lightning_intensity = 1.0
            self.lightning_timer = random.uniform(6.0, 14.0)
        else:
            self.lightning_intensity = max(0.0, self.lightning_intensity - dt * 4.5)

    def get_shake_offset(self) -> Vec3:
        if self.camera_trauma <= 0.001:
            return Vec3(0, 0, 0)
        mag = (self.camera_trauma ** 2) * 1.35
        return Vec3(
            math.sin(self.time_accum * 43.0) * mag,
            math.cos(self.time_accum * 37.0) * mag,
            math.sin(self.time_accum * 51.0) * mag * 0.7,
        )