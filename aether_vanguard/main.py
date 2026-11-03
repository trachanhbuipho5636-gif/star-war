"""
main.py - Main Game Engine & Loop for Aether Vanguard: Eclipse of Hyperion.
Run with: python main.py
"""

import os
import sys
import math
import random
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    loadPrcFileData,
    WindowProperties,
    Vec3,
    Vec4,
    Shader,
    Filename,
    DirectionalLight,
)

from config import (
    WINDOW_TITLE,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    USER_SETTINGS,
    SECTORS,
    PLAYER_MAX_HULL,
    PLAYER_FIRE_COOLDOWN,
    PLAYER_NOVA_COST,
    PLAYER_NOVA_COOLDOWN,
    MAIN_VERTEX_SHADER,
    MAIN_FRAGMENT_SHADER,
    sample_terrain_height,
)
from asset_generator import AssetGenerator, MeshFactory
from effects import ParticleSystem, WeatherAndCameraFX
from entities import PlayerShip, EnemyDrone, BossDreadnought, RelicObject, Projectile, HomingMissile
from ui_manager import UIManager

loadPrcFileData(
    "",
    f"""
    window-title {WINDOW_TITLE}
    win-size {WINDOW_WIDTH} {WINDOW_HEIGHT}
    sync-video #t
    show-frame-rate-meter #t
    hardware-animated-vertices #t
    """,
)


class AetherVanguardGame(ShowBase):
    """Main application class orchestrating 3D rendering, audio, gameplay, and UI."""

    def __init__(self):
        super().__init__()
        self.disableMouse()

        self.asset_gen = AssetGenerator("assets")
        self.asset_gen.ensure_all_assets()
        self._load_textures_and_audio()

        self.world_root = self.render.attachNewNode("WorldRoot")
        self._setup_world_shader()

        self.terrain_np = MeshFactory.create_terrain_nodepath(self.tex_terrain)
        self.terrain_np.reparentTo(self.world_root)
        self._populate_environmental_scenery()

        player_mesh = MeshFactory.create_player_ship(self.tex_hull)
        player_mesh.reparentTo(self.world_root)
        self.player = PlayerShip(player_mesh)

        self.particles = ParticleSystem(self.render, self.tex_particle)
        self.weather_fx = WeatherAndCameraFX(self.render, self.tex_particle)

        self.state = "MENU"
        self.previous_state = "MENU"
        self.sector_index = 0
        self.score = 0
        self.relics_collected = 0
        self.menu_orbit_angle = 0.0
        self.shader_time = 0.0
        self.crash_timer = 0.0
        self.crash_subburst_timer = 0.0

        self.enemies: list[EnemyDrone] = []
        self.relics: list[RelicObject] = []
        self.projectiles: list = []
        self.boss: BossDreadnought | None = None

        self.keys = {}
        self._setup_inputs()
        self.ui = UIManager(self)

        if self.bgm:
            self.bgm.setLoop(True)
            self.bgm.play()
        self.apply_audio_volume()

        self.taskMgr.add(self._update_loop, "MainGameUpdateLoop")

    def _load_textures_and_audio(self):
        def _p3d_path(subpath: str) -> Filename:
            full = os.path.abspath(os.path.join("assets", subpath))
            return Filename.fromOsSpecific(full)

        self.tex_hull = self.loader.loadTexture(_p3d_path("textures/hull_metallic.png"))
        self.tex_terrain = self.loader.loadTexture(_p3d_path("textures/terrain_grid.png"))
        self.tex_crystal = self.loader.loadTexture(_p3d_path("textures/crystal_surface.png"))
        self.tex_particle = self.loader.loadTexture(_p3d_path("textures/particle_glow.png"))

        self.sfx = {}
        for name in ("laser_shoot", "plasma_blast", "explosion", "hit_shield", "relic_pickup", "ui_click"):
            try:
                self.sfx[name] = self.loader.loadSfx(_p3d_path(f"audio/{name}.wav"))
            except Exception:
                self.sfx[name] = None

        try:
            self.bgm = self.loader.loadMusic(_p3d_path("audio/bgm_synth.wav"))
        except Exception:
            self.bgm = None

    def play_sfx(self, name: str):
        snd = self.sfx.get(name)
        if snd:
            snd.setVolume(USER_SETTINGS["audio_volume"])
            snd.play()

    def apply_audio_volume(self):
        vol = USER_SETTINGS["audio_volume"]
        if self.bgm:
            self.bgm.setVolume(vol * 0.65)
        for snd in self.sfx.values():
            if snd:
                snd.setVolume(vol)

    def _setup_world_shader(self):
        self.camLens.setFov(USER_SETTINGS["fov"])
        self.camLens.setNearFar(0.8, 950.0)
        
        # Thiết lập hướng sáng và bộ tạo bóng tự động (Shadow mapping)
        dlight = DirectionalLight("sun_shadow_light")
        dlight.setColor(Vec4(0.9, 0.9, 1.0, 1.0))
        dlight.setShadowCaster(True, 4096, 4096)
        
        dlight_np = self.world_root.attachNewNode(dlight)
        dlight_np.setHpr(45, -60, 0)
        self.world_root.setLight(dlight_np)
        
        # Kích hoạt shader tự động để hiển thị vùng bóng đổ
        self.render.setShaderAuto()

        try:
            shader = Shader.make(Shader.SL_GLSL, MAIN_VERTEX_SHADER, MAIN_FRAGMENT_SHADER)
            self.world_root.setShader(shader)
        except Exception:
            self.world_root.setShaderAuto()

        self._apply_sector_atmosphere(0)

    def _apply_sector_atmosphere(self, idx: int):
        sec = SECTORS[idx % len(SECTORS)]
        fc = sec["fog_color"]
        ac = sec["ambient_color"]
        sc = sec["sun_color"]
        self.setBackgroundColor(fc[0], fc[1], fc[2], 1.0)
        self.world_root.setShaderInput("u_light_dir", Vec3(0.45, -0.55, 0.70))
        self.world_root.setShaderInput("u_sun_color", Vec3(*sc))
        self.world_root.setShaderInput("u_ambient_color", Vec3(*ac))
        self.world_root.setShaderInput("u_fog_color", Vec3(*fc))
        self.world_root.setShaderInput("u_cam_pos", Vec3(0, 0, 20))
        self.world_root.setShaderInput("u_time", 0.0)
        self.world_root.setShaderInput("u_lightning", 0.0)

    def _populate_environmental_scenery(self):
        rng = random.Random(101)
        for i in range(42):
            angle = rng.uniform(0.0, math.pi * 2.0)
            dist = rng.uniform(45.0, 275.0)
            cx = math.cos(angle) * dist
            cy = math.sin(angle) * dist
            cz = sample_terrain_height(cx, cy)
            cluster = MeshFactory.create_crystal_cluster(self.tex_crystal, seed=i)
            cluster.setPos(cx, cy, cz)
            cluster.setH(rng.uniform(0.0, 360.0))
            cluster.reparentTo(self.world_root)

    def _setup_inputs(self):
        tracked = [
            "w", "a", "s", "d", "space", "c", "shift", "e", "1", "2",
            "mouse1", "mouse3", "arrow_left", "arrow_right", "arrow_up", "arrow_down"
        ]
        for k in tracked:
            self.keys[k] = False
            self.accept(k, self._set_key, [k, True])
            self.accept(f"{k}-up", self._set_key, [k, False])

        self.accept("escape", self._on_escape_pressed)

    def _set_key(self, key: str, value: bool):
        self.keys[key] = value

    def _set_mouse_locked(self, locked: bool):
        props = WindowProperties()
        props.setCursorHidden(locked)
        self.win.requestProperties(props)
        if locked and self.win:
            self.win.movePointer(0, int(self.win.getXSize() / 2), int(self.win.getYSize() / 2))

    def start_new_game(self):
        self.play_sfx("ui_click")
        self.score = 0
        self.sector_index = 0
        self.player.reset()
        self.particles.clear_all()
        self._load_sector(0)
        self.state = "PLAYING"
        self.ui.show_state("PLAYING")
        self._set_mouse_locked(True)

    def _load_sector(self, idx: int):
        self._clear_dynamic_entities()
        self.sector_index = idx
        self.relics_collected = 0
        sec = SECTORS[idx % len(SECTORS)]
        self._apply_sector_atmosphere(idx)

        for i in range(sec["relics_required"]):
            ang = (2.0 * math.pi * i) / sec["relics_required"] + random.uniform(-0.3, 0.3)
            dist = random.uniform(95.0, 210.0)
            rx = math.cos(ang) * dist
            ry = math.sin(ang) * dist
            rz = sample_terrain_height(rx, ry) + 8.0
            r_np, ring_np = MeshFactory.create_relic_monolith(self.tex_crystal)
            r_np.reparentTo(self.world_root)
            self.relics.append(RelicObject(r_np, ring_np, Vec3(rx, ry, rz)))

        total_drones = sec["drone_count"] + sec["elite_count"]
        for i in range(total_drones):
            is_elite = i < sec["elite_count"]
            ang = random.uniform(0.0, math.pi * 2.0)
            dist = random.uniform(75.0, 225.0)
            ex = math.cos(ang) * dist
            ey = math.sin(ang) * dist
            ez = sample_terrain_height(ex, ey) + 18.0
            d_np, ring_np = MeshFactory.create_enemy_drone(self.tex_hull, elite=is_elite)
            d_np.reparentTo(self.world_root)
            self.enemies.append(EnemyDrone(d_np, ring_np, Vec3(ex, ey, ez), elite=is_elite))

        if sec["spawn_boss"]:
            b_np, pylon_np = MeshFactory.create_boss_dreadnought(self.tex_hull)
            b_np.reparentTo(self.world_root)
            self.boss = BossDreadnought(b_np, pylon_np, Vec3(0.0, 85.0, 35.0))

        self.ui.show_banner(f"{sec['name']}\n{sec['subtitle']}", 4.0)

    def _clear_dynamic_entities(self):
        for e in self.enemies:
            e.destroy()
        self.enemies.clear()
        for r in self.relics:
            r.destroy()
        self.relics.clear()
        for p in self.projectiles:
            p.destroy()
        self.projectiles.clear()
        if self.boss:
            self.boss.destroy()
            self.boss = None

    def _on_escape_pressed(self):
        if self.state == "PLAYING":
            self.play_sfx("ui_click")
            self.state = "PAUSED"
            self.ui.show_state("PAUSED")
            self._set_mouse_locked(False)
        elif self.state == "PAUSED":
            self.resume_game()
        elif self.state == "SETTINGS":
            self.close_settings()

    def resume_game(self):
        self.play_sfx("ui_click")
        self.state = "PLAYING"
        self.ui.show_state("PLAYING")
        self._set_mouse_locked(True)

    def open_settings(self, from_state: str):
        self.play_sfx("ui_click")
        self.previous_state = from_state
        self.state = "SETTINGS"
        self.ui.show_state("SETTINGS")

    def close_settings(self):
        self.play_sfx("ui_click")
        self.state = self.previous_state
        self.ui.show_state(self.state)

    def return_to_main_menu(self):
        self.play_sfx("ui_click")
        self._clear_dynamic_entities()
        self.player.np.show()
        self.state = "MENU"
        self.ui.show_state("MENU")
        self._set_mouse_locked(False)

    def _start_crash_sequence(self):
        self.state = "CRASHING"
        self.crash_timer = 2.2
        self.crash_subburst_timer = 0.22
        self.player.np.hide()

        pos = self.player.pos
        self.particles.spawn_nova_shockwave(pos)
        self.particles.spawn_explosion(pos, Vec4(1.0, 0.55, 0.15, 1.0), scale_mult=3.2)
        self.particles.spawn_explosion(pos + Vec3(0, 0, 2.5), Vec4(0.2, 0.95, 1.0, 1.0), scale_mult=2.4)

        self.play_sfx("explosion")
        self.play_sfx("plasma_blast")
        self.weather_fx.add_trauma(1.0)
        self.ui.trigger_screen_flash((1.0, 0.45, 0.15), 0.75)

        if self.player.crashed_into_terrain:
            self.ui.show_banner("CRITICAL TERRAIN IMPACT - REACTOR DETONATION!", 2.2)
        else:
            self.ui.show_banner("HULL BREACH - REACTOR OVERLOAD!", 2.2)

    def trigger_game_over(self, victory: bool):
        self._set_mouse_locked(False)
        self.state = "GAMEOVER"
        if victory:
            self.ui.gameover_title.setText("HYPERION ECLIPSE CLEARED - VICTORY!")
            self.ui.gameover_title["fg"] = (0.25, 0.98, 0.65, 1.0)
        elif self.player.crashed_into_terrain:
            self.ui.gameover_title.setText("JET DESTROYED - TERRAIN IMPACT")
            self.ui.gameover_title["fg"] = (1.0, 0.32, 0.18, 1.0)
        else:
            self.ui.gameover_title.setText("VANGUARD INTERCEPTOR DESTROYED")
            self.ui.gameover_title["fg"] = (1.0, 0.22, 0.30, 1.0)
        self.ui.gameover_stats.setText(f"FINAL TACTICAL SCORE: {self.score:06d}")
        self.ui.show_state("GAMEOVER")

    def quit_game(self):
        self.play_sfx("ui_click")
        sys.exit(0)

    def _update_loop(self, task):
        dt = min(0.05, globalClock.getDt())
        self.shader_time += dt
        self.world_root.setShaderInput("u_time", self.shader_time)

        if self.state in ("MENU", "PAUSED", "SETTINGS", "GAMEOVER"):
            self._update_menu_camera(dt)
            self.particles.update(dt)
            return task.cont

        if self.state == "CRASHING":
            self._update_crash_cinematic(dt)
            return task.cont

        self._update_player_aim(dt)
        boosting = self.player.update(dt, self.keys, self.particles)
        self._handle_player_weapons()
        self._handle_special_abilities()

        self._update_gameplay_camera(dt, boosting)
        self._update_entities_and_collisions(dt)

        self.particles.update(dt)
        self.weather_fx.update(dt, self.player.pos, USER_SETTINGS["weather_enabled"])
        self.world_root.setShaderInput("u_lightning", self.weather_fx.lightning_intensity)

        sec_info = SECTORS[self.sector_index % len(SECTORS)]
        self.ui.update_hud(
            dt, self.player, sec_info, self.relics_collected,
            self.relics, self.enemies, self.boss, self.score
        )

        if self.player.hull <= 0.0:
            self._start_crash_sequence()
        elif (
            self.relics_collected >= sec_info["relics_required"]
            and len(self.enemies) == 0
            and (self.boss is None or not self.boss.alive)
        ):
            if self.sector_index + 1 < len(SECTORS):
                self._load_sector(self.sector_index + 1)
            else:
                self.score += 1500
                self.trigger_game_over(victory=True)

        return task.cont

    def _handle_special_abilities(self):
        if self.keys.get("1") and self.player.heal_cooldown <= 0.0:
            if self.player.hull < PLAYER_MAX_HULL:
                self.player.heal_cooldown = 8.0
                heal_amount = PLAYER_MAX_HULL * 0.2
                self.player.hull = min(PLAYER_MAX_HULL, self.player.hull + heal_amount)
                self.play_sfx("relic_pickup")
                self.ui.trigger_screen_flash((0.15, 0.95, 0.45), 0.35)
                
                for _ in range(35):
                    offset = Vec3(random.uniform(-4, 4), random.uniform(-4, 4), random.uniform(-2, 2))
                    self.particles.spawn_particle(
                        self.player.pos + offset,
                        Vec3(0, 0, random.uniform(3.0, 9.0)),
                        0.75,
                        1.5,
                        0.4,
                        Vec4(0.1, 1.0, 0.4, 0.9),
                        Vec4(0.05, 0.5, 0.2, 0.0),
                        drag=1.5
                    )
                self.ui.show_banner("EMERGENCY REPAIR APPLIED (+20% HULL)", 2.0)

        if self.keys.get("2") and self.player.rocket_cooldown <= 0.0:
            self.player.rocket_cooldown = 3.0
            self.play_sfx("plasma_blast")
            self.weather_fx.add_trauma(0.2)

            all_targets = [e for e in self.enemies if e.alive]
            if self.boss and self.boss.alive:
                all_targets.append(self.boss)

            nearest_target = None
            min_dist = float("inf")
            for t in all_targets:
                dist = (t.pos - self.player.pos).length()
                if dist < min_dist:
                    min_dist = dist
                    nearest_target = t

            rad_yaw = math.radians(self.player.yaw)
            right = Vec3(math.cos(rad_yaw), math.sin(rad_yaw), 0.0)

            for sign in (-1.8, 1.8):
                wing_pos = self.player.pos + self.aim_forward * 1.5 + right * sign
                initial_vel = self.aim_forward * 65.0 + right * (sign * 20.0)

                missile = HomingMissile(
                    self.render,
                    wing_pos,
                    initial_vel,
                    nearest_target,
                    damage=35.0,
                    color=Vec4(1.0, 0.55, 0.15, 1.0)
                )
                self.projectiles.append(missile)

            self.ui.show_banner("WING-ROCKETS DISPATCHED!", 1.5)

    def _update_crash_cinematic(self, dt: float):
        self.crash_timer -= dt
        self.crash_subburst_timer -= dt

        if self.crash_subburst_timer <= 0.0 and self.crash_timer > 0.4:
            self.crash_subburst_timer = 0.28
            offset = Vec3(
                random.uniform(-6.0, 6.0),
                random.uniform(-6.0, 6.0),
                random.uniform(0.5, 6.0),
            )
            self.particles.spawn_explosion(
                self.player.pos + offset,
                Vec4(1.0, random.uniform(0.3, 0.75), 0.15, 1.0),
                scale_mult=1.6,
            )
            self.weather_fx.add_trauma(0.35)

        self.menu_orbit_angle += 0.85 * dt
        cam_offset = Vec3(
            math.cos(self.menu_orbit_angle) * 24.0,
            math.sin(self.menu_orbit_angle) * 24.0,
            12.0,
        )
        cam_pos = self.player.pos + cam_offset
        min_z = sample_terrain_height(cam_pos.x, cam_pos.y) + 3.0
        cam_pos.z = max(min_z, cam_pos.z)

        shake = self.weather_fx.get_shake_offset()
        self.camera.setPos(cam_pos + shake)
        self.camera.lookAt(self.player.pos)
        self.world_root.setShaderInput("u_cam_pos", self.camera.getPos())

        self.particles.update(dt)
        self.weather_fx.update(dt, self.player.pos, USER_SETTINGS["weather_enabled"])
        self.ui.update_hud(
            dt, self.player, SECTORS[self.sector_index % len(SECTORS)],
            self.relics_collected, self.relics, self.enemies, self.boss, self.score
        )

        if self.crash_timer <= 0.0:
            self.trigger_game_over(victory=False)

    def _update_menu_camera(self, dt: float):
        self.menu_orbit_angle += 0.18 * dt
        rad = 115.0
        cx = math.cos(self.menu_orbit_angle) * rad
        cy = math.sin(self.menu_orbit_angle) * rad
        cz = sample_terrain_height(cx, cy) + 32.0
        self.camera.setPos(cx, cy, cz)
        self.camera.lookAt(0, 0, 10)
        self.world_root.setShaderInput("u_cam_pos", self.camera.getPos())

    def _update_player_aim(self, dt: float):
        sens = USER_SETTINGS["mouse_sensitivity"]
        if self.mouseWatcherNode.hasMouse() and self.win:
            cx = int(self.win.getXSize() / 2)
            cy = int(self.win.getYSize() / 2)
            pointer = self.win.getPointer(0)
            dx = pointer.getX() - cx
            dy = pointer.getY() - cy
            if abs(dx) > 0 or abs(dy) > 0:
                self.player.yaw -= dx * sens
                self.player.pitch = max(-75.0, min(75.0, self.player.pitch - dy * sens))
                self.win.movePointer(0, cx, cy)

        key_turn = (1.0 if self.keys.get("arrow_left") else 0.0) - (1.0 if self.keys.get("arrow_right") else 0.0)
        key_pitch = (1.0 if self.keys.get("arrow_up") else 0.0) - (1.0 if self.keys.get("arrow_down") else 0.0)
        self.player.yaw += key_turn * 95.0 * dt
        self.player.pitch = max(-75.0, min(75.0, self.player.pitch + key_pitch * 65.0 * dt))

    def _update_gameplay_camera(self, dt: float, boosting: bool):
        rad_yaw = math.radians(self.player.yaw)
        rad_pitch = math.radians(self.player.pitch)
        forward = Vec3(
            -math.sin(rad_yaw) * math.cos(rad_pitch),
            math.cos(rad_yaw) * math.cos(rad_pitch),
            math.sin(rad_pitch),
        )
        forward.normalize()
        self.aim_forward = forward

        desired_cam_pos = self.player.pos - forward * 15.5 + Vec3(0, 0, 4.2)
        min_cam_z = sample_terrain_height(desired_cam_pos.x, desired_cam_pos.y) + 2.2
        desired_cam_pos.z = max(min_cam_z, desired_cam_pos.z)

        cur_pos = self.camera.getPos()
        smooth_pos = cur_pos + (desired_cam_pos - cur_pos) * min(1.0, dt * 14.0)
        shake = self.weather_fx.get_shake_offset()
        self.camera.setPos(smooth_pos + shake)
        self.camera.lookAt(self.player.pos + forward * 45.0)
        self.world_root.setShaderInput("u_cam_pos", self.camera.getPos())

        target_fov = USER_SETTINGS["fov"] + (9.0 if boosting else 0.0)
        cur_fov = self.camLens.getFov()[0]
        self.camLens.setFov(cur_fov + (target_fov - cur_fov) * min(1.0, dt * 8.0))

    def _handle_player_weapons(self):
        if self.keys.get("mouse1") and self.player.fire_timer <= 0.0:
            self.player.fire_timer = PLAYER_FIRE_COOLDOWN
            self.play_sfx("laser_shoot")
            
            rad_yaw = math.radians(self.player.yaw)
            rad_pitch = math.radians(self.player.pitch)
            forward = Vec3(
                -math.sin(rad_yaw) * math.cos(rad_pitch),
                math.cos(rad_yaw) * math.cos(rad_pitch),
                math.sin(rad_pitch),
            )
            forward.normalize()
            right = Vec3(math.cos(rad_yaw), math.sin(rad_yaw), 0.0)
            
            for sign in (-3.0, 3.0):
                muzzle_pos = self.player.pos + forward * 2.5 + right * sign
                bolt = Projectile(
                    self.render,
                    muzzle_pos,
                    forward * 165.0 + self.player.vel * 0.25,
                    is_player=True,
                    damage=16.0,
                    # Màu xanh neon điện tử cực sáng (Neon Blue)
                    color=Vec4(0.0, 0.85, 1.0, 1.0),
                )
                self.projectiles.append(bolt)

        if (
            (self.keys.get("mouse3") or self.keys.get("e"))
            and self.player.nova_timer <= 0.0
            and self.player.energy >= PLAYER_NOVA_COST
        ):
            self.player.nova_timer = PLAYER_NOVA_COOLDOWN
            self.player.energy -= PLAYER_NOVA_COST
            self.play_sfx("plasma_blast")
            self.weather_fx.add_trauma(0.45)
            self.ui.trigger_screen_flash((0.2, 0.85, 1.0), 0.30)
            self.particles.spawn_nova_shockwave(self.player.pos)

            for enemy in list(self.enemies):
                if enemy.alive and (enemy.pos - self.player.pos).length() <= 65.0:
                    enemy.hp -= 55.0
                    self.particles.spawn_hit_sparks(enemy.pos, Vec4(0.3, 0.95, 1.0, 1.0))
                    if enemy.hp <= 0.0:
                        self._on_enemy_destroyed(enemy)

            if self.boss and self.boss.alive and (self.boss.pos - self.player.pos).length() <= 75.0:
                self.boss.hp -= 65.0
                self.particles.spawn_hit_sparks(self.boss.pos, Vec4(1.0, 0.4, 0.8, 1.0))
                if self.boss.hp <= 0.0:
                    self._on_boss_destroyed()

    def _update_entities_and_collisions(self, dt: float):
        for relic in list(self.relics):
            if not relic.alive:
                continue
            relic.update(dt)
            if (relic.base_pos - self.player.pos).length() <= 11.5:
                relic.destroy()
                self.relics.remove(relic)
                self.relics_collected += 1
                self.score += 500
                self.player.shield = min(100.0, self.player.shield + 30.0)
                self.player.hull = min(100.0, self.player.hull + 15.0)
                self.play_sfx("relic_pickup")
                self.ui.trigger_screen_flash((0.15, 0.95, 0.75), 0.32)
                self.particles.spawn_explosion(relic.base_pos, Vec4(0.15, 0.98, 0.85, 1.0), scale_mult=1.2)
                self.ui.show_banner("DATA RELIC EXTRACTED (+30 SHIELD / +500 PTS)", 2.2)

        for enemy in list(self.enemies):
            if not enemy.alive:
                continue
            should_fire, aim_dir = enemy.update(dt, self.player.pos, self.player.vel)
            if should_fire:
                bolt = Projectile(
                    self.render,
                    enemy.pos + aim_dir * 2.2,
                    aim_dir * 95.0,
                    is_player=False,
                    damage=14.0 if enemy.elite else 9.0,
                    color=Vec4(1.0, 0.22, 0.25, 1.0),
                )
                self.projectiles.append(bolt)

        if self.boss and self.boss.alive:
            fire_dirs = self.boss.update(dt, self.player.pos)
            for f_dir in fire_dirs:
                bolt = Projectile(
                    self.render,
                    self.boss.pos + f_dir * 6.5,
                    f_dir * 105.0,
                    is_player=False,
                    damage=16.0,
                    color=Vec4(1.0, 0.15, 0.65, 1.0),
                )
                self.projectiles.append(bolt)

        alive_projectiles = []
        for proj in self.projectiles:
            if isinstance(proj, HomingMissile):
                if not proj.update(dt, self.particles):
                    continue
                p_pos = proj.np.getPos()
                hit = False
                for enemy in list(self.enemies):
                    if enemy.alive and (p_pos - enemy.pos).length() <= enemy.radius + 1.5:
                        enemy.hp -= proj.damage
                        self.particles.spawn_hit_sparks(p_pos, Vec4(1.0, 0.6, 0.2, 1.0))
                        proj.destroy()
                        hit = True
                        if enemy.hp <= 0.0:
                            self._on_enemy_destroyed(enemy)
                        break

                if not hit and self.boss and self.boss.alive:
                    if (p_pos - self.boss.pos).length() <= self.boss.radius + 1.5:
                        self.boss.hp -= proj.damage
                        self.particles.spawn_hit_sparks(p_pos, Vec4(1.0, 0.6, 0.2, 1.0))
                        proj.destroy()
                        hit = True
                        if self.boss.hp <= 0.0:
                            self._on_boss_destroyed()

                if not hit:
                    alive_projectiles.append(proj)
                continue

            if not proj.update(dt):
                continue

            p_pos = proj.np.getPos()
            if proj.is_player:
                hit = False
                for enemy in list(self.enemies):
                    if enemy.alive and (p_pos - enemy.pos).length() <= enemy.radius + 1.1:
                        enemy.hp -= proj.damage
                        self.particles.spawn_hit_sparks(p_pos, Vec4(0.2, 0.9, 1.0, 1.0))
                        proj.destroy()
                        hit = True
                        if enemy.hp <= 0.0:
                            self._on_enemy_destroyed(enemy)
                        break

                if not hit and self.boss and self.boss.alive:
                    if (p_pos - self.boss.pos).length() <= self.boss.radius + 1.2:
                        self.boss.hp -= proj.damage
                        self.particles.spawn_hit_sparks(p_pos, Vec4(1.0, 0.4, 0.8, 1.0))
                        proj.destroy()
                        hit = True
                        if self.boss.hp <= 0.0:
                            self._on_boss_destroyed()

                if not hit:
                    ground_z = sample_terrain_height(p_pos.x, p_pos.y)
                    if p_pos.z <= ground_z + 0.8:
                        self.particles.spawn_hit_sparks(p_pos, Vec4(0.4, 0.8, 1.0, 0.8))
                        proj.destroy()
                    else:
                        alive_projectiles.append(proj)
            else:
                if (p_pos - self.player.pos).length() <= 3.0:
                    shield_hit = self.player.take_damage(proj.damage)
                    self.play_sfx("hit_shield")
                    self.weather_fx.add_trauma(0.32)
                    flash_col = (0.15, 0.75, 1.0) if shield_hit else (1.0, 0.15, 0.2)
                    self.ui.trigger_screen_flash(flash_col, 0.32)
                    self.particles.spawn_hit_sparks(p_pos, Vec4(1.0, 0.3, 0.2, 1.0))
                    proj.destroy()
                else:
                    alive_projectiles.append(proj)

        self.projectiles = alive_projectiles

    def _on_enemy_destroyed(self, enemy: EnemyDrone):
        pos = Vec3(enemy.pos)
        self.score += enemy.score_value
        enemy.destroy()
        if enemy in self.enemies:
            self.enemies.remove(enemy)
        self.play_sfx("explosion")
        self.weather_fx.add_trauma(0.22)
        self.particles.spawn_explosion(pos, Vec4(1.0, 0.55, 0.15, 1.0), scale_mult=1.25 if enemy.elite else 1.0)

    def _on_boss_destroyed(self):
        if not self.boss:
            return
        pos = Vec3(self.boss.pos)
        self.score += self.boss.score_value
        self.boss.destroy()
        self.boss = None
        self.play_sfx("explosion")
        self.weather_fx.add_trauma(0.85)
        self.particles.spawn_explosion(pos, Vec4(1.0, 0.25, 0.65, 1.0), scale_mult=2.8)
        self.ui.show_banner("HYPERION SIEGE DREADNOUGHT DESTROYED! (+2500 PTS)", 3.5)


if __name__ == "__main__":
    app = AetherVanguardGame()
    app.run()
