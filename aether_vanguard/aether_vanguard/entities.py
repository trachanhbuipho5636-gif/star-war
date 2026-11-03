"""
entities.py - Gameplay Entities: Free-Flight Player, Projectiles, Drones, Boss, and Relics.
"""

import math
import random
from panda3d.core import NodePath, Vec3, Vec4, CardMaker

from config import (
    PLAYER_MAX_HULL,
    PLAYER_MAX_SHIELD,
    PLAYER_MAX_ENERGY,
    SHIELD_REGEN_RATE,
    SHIELD_REGEN_DELAY,
    ENERGY_REGEN_RATE,
    PLAYER_ACCEL,
    PLAYER_BOOST_MULT,
    PLAYER_DRAG,
    BOUNDARY_RADIUS,
    sample_terrain_height,
)


class Projectile:
    """Tia đạn laser neon xanh dương rực rỡ, tự động tăng tốc và bay mượt mà."""

    def __init__(self, parent_np: NodePath, pos: Vec3, vel: Vec3, is_player: bool, damage: float, color: Vec4):
        cm = CardMaker("bolt")
        cm.setFrame(-0.35, 0.35, -0.35, 0.35)
        self.np = parent_np.attachNewNode(cm.generate())
        self.np.setBillboardPointEye()
        self.np.setLightOff()
        self.np.setShaderOff()
        self.np.setScale(1.6 if is_player else 1.8)
        self.np.setColor(color)
        self.np.setPos(pos)

        self.vel = Vec3(vel)
        self.is_player = is_player
        self.damage = damage
        self.lifetime = 2.5
        self.alive = True

    def update(self, dt: float) -> bool:
        if not self.alive:
            return False
        self.lifetime -= dt
        if self.lifetime <= 0.0:
            self.destroy()
            return False

        self.vel *= (1.0 + 2.2 * dt)

        new_pos = self.np.getPos() + self.vel * dt
        if new_pos.z <= sample_terrain_height(new_pos.x, new_pos.y) + 0.5:
            self.destroy()
            return False

        self.np.setPos(new_pos)
        return True

    def destroy(self):
        if self.alive:
            self.alive = False
            self.np.removeNode()


class HomingMissile:
    """Tên lửa bám đuôi phóng từ cánh với hiệu ứng khói phía sau."""

    def __init__(self, parent_np: NodePath, pos: Vec3, initial_vel: Vec3, target_entity, damage: float, color: Vec4):
        cm = CardMaker("missile")
        cm.setFrame(-0.45, 0.45, -0.45, 0.45)
        self.np = parent_np.attachNewNode(cm.generate())
        self.np.setBillboardPointEye()
        self.np.setLightOff()
        self.np.setShaderOff()
        self.np.setScale(1.7)
        self.np.setColor(color)
        self.np.setPos(pos)

        self.pos = Vec3(pos)
        self.vel = Vec3(initial_vel)
        self.target = target_entity
        self.damage = damage
        self.lifetime = 4.5
        self.alive = True
        self.smoke_timer = 0.0

    def update(self, dt: float, particle_system=None) -> bool:
        if not self.alive:
            return False
        self.lifetime -= dt
        if self.lifetime <= 0.0:
            self.destroy()
            return False

        self.smoke_timer -= dt
        if self.smoke_timer <= 0.0 and particle_system:
            self.smoke_timer = 0.035
            particle_system.spawn_particle(
                self.pos,
                -self.vel * 0.15 + Vec3(random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1)),
                0.35,
                1.1,
                0.3,
                Vec4(0.85, 0.85, 0.85, 0.5),
                Vec4(0.3, 0.3, 0.3, 0.0),
                drag=2.0
            )

        if self.target and getattr(self.target, "alive", False):
            target_pos = self.target.pos
            to_target = target_pos - self.pos
            dist = to_target.length()
            if dist > 0.1:
                dir_to_target = to_target / dist
                self.vel = self.vel + dir_to_target * (165.0 * dt)
                if self.vel.lengthSquared() > 155.0**2:
                    self.vel.normalize()
                    self.vel *= 155.0

        new_pos = self.pos + self.vel * dt
        if new_pos.z <= sample_terrain_height(new_pos.x, new_pos.y) + 0.5:
            if particle_system:
                particle_system.spawn_explosion(new_pos, Vec4(1.0, 0.5, 0.2, 1.0), scale_mult=0.8)
            self.destroy()
            return False

        self.pos = new_pos
        self.np.setPos(self.pos)
        return True

    def destroy(self):
        if self.alive:
            self.alive = False
            self.np.removeNode()


class PlayerShip:
    """Phi thuyền người chơi tự do 3D."""

    def __init__(self, model_np: NodePath):
        self.np = model_np
        self.reset()

    def reset(self):
        start_ground = sample_terrain_height(0.0, -60.0)
        self.pos = Vec3(0.0, -60.0, start_ground + 28.0)
        self.vel = Vec3(0.0, 0.0, 0.0)
        self.yaw = 0.0
        self.pitch = 0.0
        self.visual_roll = 0.0
        self.visual_pitch = 0.0

        self.hull = PLAYER_MAX_HULL
        self.shield = PLAYER_MAX_SHIELD
        self.energy = PLAYER_MAX_ENERGY
        self.shield_delay_timer = 0.0
        self.fire_timer = 0.0
        self.nova_timer = 0.0
        self.heal_cooldown = 0.0
        self.rocket_cooldown = 0.0
        self.thruster_emit_timer = 0.0
        self.crashed_into_terrain = False
        self.altitude_above_ground = 28.0

        self.np.show()
        self.np.setPos(self.pos)
        self.np.setHpr(self.yaw, 0.0, 0.0)

    def take_damage(self, amount: float) -> bool:
        self.shield_delay_timer = SHIELD_REGEN_DELAY
        if self.shield > 0.0:
            absorbed = min(self.shield, amount)
            self.shield -= absorbed
            remainder = amount - absorbed
            if remainder > 0.0:
                self.hull = max(0.0, self.hull - remainder)
            return True
        self.hull = max(0.0, self.hull - amount)
        return False

    def update(self, dt: float, keys: dict, particles) -> bool:
        if self.shield_delay_timer > 0.0:
            self.shield_delay_timer -= dt
        elif self.shield < PLAYER_MAX_SHIELD:
            self.shield = min(PLAYER_MAX_SHIELD, self.shield + SHIELD_REGEN_RATE * dt)

        self.fire_timer = max(0.0, self.fire_timer - dt)
        self.nova_timer = max(0.0, self.nova_timer - dt)
        self.heal_cooldown = max(0.0, self.heal_cooldown - dt)
        self.rocket_cooldown = max(0.0, self.rocket_cooldown - dt)

        rad_yaw = math.radians(self.yaw)
        rad_pitch = math.radians(self.pitch)
        forward = Vec3(
            -math.sin(rad_yaw) * math.cos(rad_pitch),
            math.cos(rad_yaw) * math.cos(rad_pitch),
            math.sin(rad_pitch),
        )
        forward.normalize()
        right = Vec3(math.cos(rad_yaw), math.sin(rad_yaw), 0.0)
        up_vec = Vec3(0.0, 0.0, 1.0)

        move_f = (1.0 if keys.get("w") else 0.0) - (1.0 if keys.get("s") else 0.0)
        move_r = (1.0 if keys.get("d") else 0.0) - (1.0 if keys.get("a") else 0.0)
        move_up = (1.0 if keys.get("space") else 0.0) - (1.0 if keys.get("c") else 0.0)

        is_moving = abs(move_f) > 0.1 or abs(move_r) > 0.1 or abs(move_up) > 0.1
        boosting = bool(keys.get("shift")) and is_moving and self.energy > 5.0
        speed_mult = 1.0
        if boosting:
            speed_mult = PLAYER_BOOST_MULT
            self.energy = max(0.0, self.energy - 26.0 * dt)
        else:
            self.energy = min(PLAYER_MAX_ENERGY, self.energy + ENERGY_REGEN_RATE * dt)

        wish_dir = forward * move_f + right * move_r + up_vec * (move_up * 0.85)
        if wish_dir.lengthSquared() > 1.0:
            wish_dir.normalize()

        self.vel += wish_dir * (PLAYER_ACCEL * speed_mult * dt)
        self.vel *= max(0.0, 1.0 - PLAYER_DRAG * dt)
        self.pos += self.vel * dt

        if self.pos.z > 280.0:
            self.pos.z = 280.0
            if self.vel.z > 0.0:
                self.vel.z = 0.0

        ground_z = sample_terrain_height(self.pos.x, self.pos.y)
        self.altitude_above_ground = self.pos.z - ground_z
        if self.pos.z <= ground_z + 1.5:
            self.pos.z = ground_z + 1.5
            self.hull = 0.0
            self.crashed_into_terrain = True

        dist_origin = math.hypot(self.pos.x, self.pos.y)
        if dist_origin > BOUNDARY_RADIUS:
            pull_dir = Vec3(-self.pos.x / dist_origin, -self.pos.y / dist_origin, 0.0)
            self.vel += pull_dir * ((dist_origin - BOUNDARY_RADIUS) * 9.0 * dt)

        target_roll = move_r * 34.0
        self.visual_roll += (target_roll - self.visual_roll) * min(1.0, dt * 10.0)
        self.visual_pitch += (self.pitch - self.visual_pitch) * min(1.0, dt * 12.0)

        self.np.setPos(self.pos)
        self.np.setHpr(self.yaw, self.visual_pitch, self.visual_roll)

        self.thruster_emit_timer -= dt
        if self.thruster_emit_timer <= 0.0:
            self.thruster_emit_timer = 0.025 if boosting else 0.045
            p_col = Vec4(0.2, 0.95, 1.0, 0.9) if boosting else Vec4(0.15, 0.65, 1.0, 0.7)
            for sign in (-0.85, 0.85):
                exhaust_pos = self.pos - forward * 2.75 + right * sign
                particles.spawn_particle(
                    exhaust_pos,
                    -forward * (28.0 if boosting else 14.0),
                    0.24,
                    1.25 if boosting else 0.85,
                    0.15,
                    p_col,
                    Vec4(0.05, 0.2, 0.9, 0.0),
                )
        return boosting


class EnemyDrone:
    """Drone địch tự động nhắm bắn."""

    def __init__(self, root_np: NodePath, ring_np: NodePath, pos: Vec3, elite: bool = False):
        self.np = root_np
        self.ring_np = ring_np
        self.pos = Vec3(pos)
        self.vel = Vec3(0, 0, 0)
        self.elite = elite
        self.max_hp = 85.0 if elite else 42.0
        self.hp = self.max_hp
        self.radius = 2.6 if elite else 2.0
        self.score_value = 350 if elite else 150

        self.fire_cooldown = random.uniform(0.8, 1.8)
        self.strafe_dir = random.choice([-1.0, 1.0])
        self.strafe_switch_timer = random.uniform(2.5, 5.0)
        self.alive = True
        self.np.setPos(self.pos)

    def update(self, dt: float, player_pos: Vec3, player_vel: Vec3) -> tuple:
        if not self.alive:
            return False, Vec3(0, 1, 0)

        self.ring_np.setH(self.ring_np.getH() + (210.0 if self.elite else 135.0) * dt)
        self.ring_np.setR(math.sin(self.fire_cooldown * 3.0) * 18.0)

        self.strafe_switch_timer -= dt
        if self.strafe_switch_timer <= 0.0:
            self.strafe_dir *= -1.0
            self.strafe_switch_timer = random.uniform(2.5, 5.0)

        to_player = player_pos - self.pos
        dist = max(0.001, to_player.length())
        dir_to_player = to_player / dist

        right_vec = Vec3(-dir_to_player.y, dir_to_player.x, 0.0)
        optimal_dist = 42.0 if self.elite else 34.0
        radial_factor = max(-1.0, min(1.0, (dist - optimal_dist) / 22.0))

        move_speed = 34.0 if self.elite else 26.0
        desired_vel = (dir_to_player * radial_factor + right_vec * (0.75 * self.strafe_dir)) * move_speed
        self.vel += (desired_vel - self.vel) * min(1.0, dt * 4.0)
        self.pos += self.vel * dt

        ground_z = sample_terrain_height(self.pos.x, self.pos.y)
        target_z = max(ground_z + 10.5, player_pos.z + (3.5 if self.elite else 1.5))
        self.pos.z += (target_z - self.pos.z) * min(1.0, dt * 5.0)

        self.np.setPos(self.pos)
        self.np.lookAt(player_pos)

        self.fire_cooldown -= dt
        if self.fire_cooldown <= 0.0 and dist < 145.0:
            self.fire_cooldown = random.uniform(0.95, 1.55) if self.elite else random.uniform(1.4, 2.3)
            aim_dir = player_pos - self.pos
            if aim_dir.lengthSquared() > 1e-6:
                aim_dir.normalize()
            return True, aim_dir

        return False, dir_to_player

    def destroy(self):
        if self.alive:
            self.alive = False
            self.np.removeNode()


class BossDreadnought:
    """Boss Dreadnought."""

    def __init__(self, root_np: NodePath, pylon_np: NodePath, pos: Vec3):
        self.np = root_np
        self.pylon_np = pylon_np
        self.pos = Vec3(pos)
        self.max_hp = 650.0
        self.hp = self.max_hp
        self.radius = 7.8
        self.score_value = 2500
        self.orbit_angle = 0.0
        self.fire_timer = 1.5
        self.alive = True
        self.np.setPos(self.pos)

    def update(self, dt: float, player_pos: Vec3) -> list[Vec3]:
        if not self.alive:
            return []

        self.orbit_angle += 0.22 * dt
        self.pylon_np.setH(self.pylon_np.getH() + 85.0 * dt)

        target_x = math.cos(self.orbit_angle) * 65.0
        target_y = math.sin(self.orbit_angle) * 65.0
        ground_z = sample_terrain_height(target_x, target_y)
        target_pos = Vec3(target_x, target_y, max(ground_z + 26.0, player_pos.z + 8.0))

        self.pos += (target_pos - self.pos) * min(1.0, dt * 2.5)
        self.np.setPos(self.pos)
        self.np.lookAt(player_pos)

        self.fire_timer -= dt
        shots = []
        if self.fire_timer <= 0.0:
            self.fire_timer = 1.15
            base_dir = player_pos - self.pos
            if base_dir.lengthSquared() > 1e-6:
                base_dir.normalize()
                for spread_deg in (-10.0, 0.0, 10.0):
                    rad = math.radians(spread_deg)
                    ca, sa = math.cos(rad), math.sin(rad)
                    sx = base_dir.x * ca - base_dir.y * sa
                    sy = base_dir.x * sa + base_dir.y * ca
                    shots.append(Vec3(sx, sy, base_dir.z))
        return shots

    def destroy(self):
        if self.alive:
            self.alive = False
            self.np.removeNode()


class RelicObject:
    """Vật phẩm Data Relic."""

    def __init__(self, root_np: NodePath, ring_np: NodePath, pos: Vec3):
        self.np = root_np
        self.ring_np = ring_np
        self.base_pos = Vec3(pos)
        self.phase = random.uniform(0.0, math.pi * 2.0)
        self.alive = True
        self.np.setPos(self.base_pos)

    def update(self, dt: float):
        if not self.alive:
            return
        self.phase += dt * 2.6
        bob_z = math.sin(self.phase) * 1.15
        self.np.setPos(self.base_pos.x, self.base_pos.y, self.base_pos.z + bob_z)
        self.np.setH(self.np.getH() + 55.0 * dt)
        self.ring_np.setP(self.ring_np.getP() + 110.0 * dt)
        self.ring_np.setR(self.ring_np.getR() + 75.0 * dt)

    def destroy(self):
        if self.alive:
            self.alive = False
            self.np.removeNode()