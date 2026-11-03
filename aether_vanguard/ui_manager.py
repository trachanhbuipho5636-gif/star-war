"""
ui_manager.py - Tactical HUD, Real-Time Radar Minimap, and Menu System.
"""

import math
from direct.gui.DirectGui import DirectFrame, DirectButton, DirectSlider, OnscreenText, DGG
from panda3d.core import TextNode, TransparencyAttrib, Vec4

from config import (
    USER_SETTINGS,
    PLAYER_MAX_HULL,
    PLAYER_MAX_SHIELD,
    PLAYER_MAX_ENERGY,
)


class UIManager:
    """Manages all 2D HUD elements, radar blips, and interactive menus."""

    def __init__(self, app):
        self.app = app

        # Build HUD & Menu hierarchies on aspect2d
        self.hud_root = DirectFrame(parent=app.aspect2d, frameColor=(0, 0, 0, 0))
        self.menu_root = DirectFrame(parent=app.aspect2d, frameColor=(0, 0, 0, 0.65), frameSize=(-2.0, 2.0, -1.0, 1.0))
        self.pause_root = DirectFrame(parent=app.aspect2d, frameColor=(0, 0, 0, 0.72), frameSize=(-2.0, 2.0, -1.0, 1.0))
        self.settings_root = DirectFrame(parent=app.aspect2d, frameColor=(0.02, 0.05, 0.12, 0.88), frameSize=(-2.0, 2.0, -1.0, 1.0))
        self.gameover_root = DirectFrame(parent=app.aspect2d, frameColor=(0.04, 0.02, 0.06, 0.85), frameSize=(-2.0, 2.0, -1.0, 1.0))

        # Fullscreen damage/pickup screen flash overlay
        self.flash_frame = DirectFrame(
            parent=app.render2d,
            frameColor=(1.0, 0.1, 0.2, 0.0),
            frameSize=(-1.0, 1.0, -1.0, 1.0),
        )
        self.flash_frame.setTransparency(TransparencyAttrib.MAlpha)
        self.flash_alpha = 0.0
        self.flash_color = (1.0, 0.15, 0.2)

        self._build_hud()
        self._build_main_menu()
        self._build_pause_menu()
        self._build_settings_menu()
        self._build_gameover_menu()

        self.show_state("MENU")

    def _make_button(self, parent, text: str, pos: tuple, command, width: float = 0.34):
        return DirectButton(
            parent=parent,
            text=text,
            pos=pos,
            scale=0.055,
            frameSize=(-width / 0.055, width / 0.055, -0.65, 1.15),
            frameColor=(0.08, 0.22, 0.38, 0.92),
            text_fg=(0.88, 0.96, 1.0, 1.0),
            relief=DGG.FLAT,
            command=command,
        )

    def _build_hud(self):
        # Status Bars (Bottom-Left)
        self.hull_bg, self.hull_fill, self.hull_txt = self._create_bar(
            -1.25, -0.74, "HULL INTEGRITY", (0.95, 0.25, 0.32, 0.95)
        )
        self.shield_bg, self.shield_fill, self.shield_txt = self._create_bar(
            -1.25, -0.83, "AETHER SHIELD", (0.15, 0.82, 1.0, 0.95)
        )
        self.energy_bg, self.energy_fill, self.energy_txt = self._create_bar(
            -1.25, -0.92, "THRUSTER / NOVA CAPACITOR", (1.0, 0.75, 0.18, 0.95)
        )

        # Top-Left Sector & Objective Readout
        self.sector_text = OnscreenText(
            parent=self.hud_root,
            text="SECTOR 1",
            pos=(-1.28, 0.90),
            scale=0.052,
            fg=(0.25, 0.92, 1.0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.objective_text = OnscreenText(
            parent=self.hud_root,
            text="Relics Extracted: 0 / 3   |   Hostiles Remaining: 0",
            pos=(-1.28, 0.83),
            scale=0.040,
            fg=(0.85, 0.92, 0.98, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
        )

        # Top-Right Score & Controls Reminder
        self.score_text = OnscreenText(
            parent=self.hud_root,
            text="SCORE: 000000",
            pos=(1.28, 0.90),
            scale=0.055,
            fg=(1.0, 0.82, 0.25, 1.0),
            align=TextNode.ARight,
            mayChange=True,
        )
        self.controls_hint = OnscreenText(
            parent=self.hud_root,
            text="[WASD] Fly  [SHIFT] Boost  [SPACE/C] Alt  [LMB] Pulse Laser  [RMB/E] Nova Shockwave  [ESC] Pause",
            pos=(0.0, -0.96),
            scale=0.032,
            fg=(0.65, 0.78, 0.90, 0.85),
            align=TextNode.ACenter,
            mayChange=False,
        )

        # Center Tactical Reticle
        self.reticle_outer = OnscreenText(
            parent=self.hud_root,
            text="[  +  ]",
            pos=(0.0, -0.015),
            scale=0.052,
            fg=(0.2, 0.95, 1.0, 0.85),
            align=TextNode.ACenter,
        )

        # Boss Health Bar (Top-Center, hidden unless Boss is active)
        self.boss_bar_bg = DirectFrame(
            parent=self.hud_root,
            pos=(-0.45, 0, 0.74),
            frameSize=(0.0, 0.90, -0.022, 0.022),
            frameColor=(0.12, 0.04, 0.08, 0.85),
        )
        self.boss_bar_fill = DirectFrame(
            parent=self.boss_bar_bg,
            pos=(0, 0, 0),
            frameSize=(0.0, 0.90, -0.018, 0.018),
            frameColor=(1.0, 0.15, 0.32, 0.95),
        )
        self.boss_bar_label = OnscreenText(
            parent=self.boss_bar_bg,
            text="HYPERION SIEGE DREADNOUGHT",
            pos=(0.45, 0.035),
            scale=0.038,
            fg=(1.0, 0.35, 0.45, 1.0),
            align=TextNode.ACenter,
        )
        self.boss_bar_bg.hide()

        # Center Banner Notification
        self.banner_text = OnscreenText(
            parent=self.hud_root,
            text="",
            pos=(0.0, 0.32),
            scale=0.068,
            fg=(0.3, 0.95, 1.0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.banner_timer = 0.0

        # 2D Radar / Minimap (Bottom-Right)
        self.radar_radius = 0.20
        self.radar_frame = DirectFrame(
            parent=self.hud_root,
            pos=(1.05, 0, -0.72),
            frameSize=(-self.radar_radius, self.radar_radius, -self.radar_radius, self.radar_radius),
            frameColor=(0.03, 0.09, 0.18, 0.82),
        )
        OnscreenText(
            parent=self.radar_frame,
            text="TACTICAL RADAR",
            pos=(0.0, self.radar_radius + 0.02),
            scale=0.032,
            fg=(0.35, 0.88, 1.0, 0.9),
        )
        # Player center triangle indicator
        DirectFrame(
            parent=self.radar_frame,
            pos=(0, 0, 0),
            frameSize=(-0.012, 0.012, -0.012, 0.012),
            frameColor=(1.0, 1.0, 1.0, 1.0),
        )
        self.radar_blips = []
        for _ in range(25):
            blip = DirectFrame(
                parent=self.radar_frame,
                pos=(0, 0, 0),
                frameSize=(-0.011, 0.011, -0.011, 0.011),
                frameColor=(1.0, 0.2, 0.2, 1.0),
            )
            blip.hide()
            self.radar_blips.append(blip)

    def _create_bar(self, x: float, y: float, label: str, color: tuple):
        bg = DirectFrame(
            parent=self.hud_root,
            pos=(x, 0, y),
            frameSize=(0.0, 0.52, -0.018, 0.018),
            frameColor=(0.05, 0.08, 0.14, 0.85),
        )
        fill = DirectFrame(
            parent=bg,
            pos=(0, 0, 0),
            frameSize=(0.0, 0.52, -0.014, 0.014),
            frameColor=color,
        )
        txt = OnscreenText(
            parent=bg,
            text=label,
            pos=(0.01, 0.024),
            scale=0.029,
            fg=(0.82, 0.92, 1.0, 0.95),
            align=TextNode.ALeft,
            mayChange=True,
        )
        return bg, fill, txt

    def _build_main_menu(self):
        OnscreenText(
            parent=self.menu_root,
            text="AETHER VANGUARD",
            pos=(0.0, 0.52),
            scale=0.115,
            fg=(0.22, 0.92, 1.0, 1.0),
        )
        OnscreenText(
            parent=self.menu_root,
            text="E C L I P S E   O F   H Y P E R I O N",
            pos=(0.0, 0.40),
            scale=0.048,
            fg=(0.88, 0.72, 0.30, 1.0),
        )
        self._make_button(self.menu_root, "LAUNCH SORTIE", (0, 0, 0.12), self.app.start_new_game)
        self._make_button(self.menu_root, "SYSTEM SETTINGS", (0, 0, -0.04), lambda: self.app.open_settings("MENU"))
        self._make_button(self.menu_root, "EXIT TO DESKTOP", (0, 0, -0.20), self.app.quit_game)

    def _build_pause_menu(self):
        OnscreenText(
            parent=self.pause_root,
            text="MISSION PAUSED",
            pos=(0.0, 0.42),
            scale=0.09,
            fg=(0.25, 0.92, 1.0, 1.0),
        )
        self._make_button(self.pause_root, "RESUME SORTIE", (0, 0, 0.14), self.app.resume_game)
        self._make_button(self.pause_root, "SYSTEM SETTINGS", (0, 0, -0.02), lambda: self.app.open_settings("PAUSED"))
        self._make_button(self.pause_root, "ABORT TO MAIN MENU", (0, 0, -0.18), self.app.return_to_main_menu)

    def _build_settings_menu(self):
        OnscreenText(
            parent=self.settings_root,
            text="TACTICAL SYSTEM SETTINGS",
            pos=(0.0, 0.58),
            scale=0.08,
            fg=(0.25, 0.92, 1.0, 1.0),
        )

        # Mouse Sensitivity Slider
        self.sens_label = OnscreenText(
            parent=self.settings_root,
            text=f"Mouse Aim Sensitivity: {USER_SETTINGS['mouse_sensitivity']:.2f}",
            pos=(0.0, 0.36),
            scale=0.045,
            fg=(0.9, 0.95, 1.0, 1.0),
            mayChange=True,
        )
        self.sens_slider = DirectSlider(
            parent=self.settings_root,
            pos=(0, 0, 0.28),
            scale=0.45,
            range=(0.05, 0.40),
            value=USER_SETTINGS["mouse_sensitivity"],
            command=self._on_sens_changed,
        )

        # Audio Volume Slider
        self.vol_label = OnscreenText(
            parent=self.settings_root,
            text=f"Master Audio Volume: {int(USER_SETTINGS['audio_volume'] * 100)}%",
            pos=(0.0, 0.14),
            scale=0.045,
            fg=(0.9, 0.95, 1.0, 1.0),
            mayChange=True,
        )
        self.vol_slider = DirectSlider(
            parent=self.settings_root,
            pos=(0, 0, 0.06),
            scale=0.45,
            range=(0.0, 1.0),
            value=USER_SETTINGS["audio_volume"],
            command=self._on_vol_changed,
        )

        # FOV Slider
        self.fov_label = OnscreenText(
            parent=self.settings_root,
            text=f"Camera Field of View: {int(USER_SETTINGS['fov'])} deg",
            pos=(0.0, -0.08),
            scale=0.045,
            fg=(0.9, 0.95, 1.0, 1.0),
            mayChange=True,
        )
        self.fov_slider = DirectSlider(
            parent=self.settings_root,
            pos=(0, 0, -0.16),
            scale=0.45,
            range=(55.0, 90.0),
            value=USER_SETTINGS["fov"],
            command=self._on_fov_changed,
        )

        # Dynamic Weather Toggle
        self.weather_btn = self._make_button(
            self.settings_root,
            "ION STORM WEATHER: ON",
            (0, 0, -0.34),
            self._toggle_weather,
            width=0.42,
        )
        self._make_button(self.settings_root, "BACK", (0, 0, -0.52), self.app.close_settings)

    def _build_gameover_menu(self):
        self.gameover_title = OnscreenText(
            parent=self.gameover_root,
            text="MISSION COMPLETE",
            pos=(0.0, 0.45),
            scale=0.095,
            fg=(0.25, 0.95, 0.65, 1.0),
            mayChange=True,
        )
        self.gameover_stats = OnscreenText(
            parent=self.gameover_root,
            text="FINAL SCORE: 0",
            pos=(0.0, 0.25),
            scale=0.055,
            fg=(1.0, 0.85, 0.3, 1.0),
            mayChange=True,
        )
        self._make_button(self.gameover_root, "DEPLOY AGAIN", (0, 0, 0.02), self.app.start_new_game)
        self._make_button(self.gameover_root, "MAIN MENU", (0, 0, -0.15), self.app.return_to_main_menu)

    def _on_sens_changed(self):
        val = self.sens_slider["value"]
        USER_SETTINGS["mouse_sensitivity"] = val
        self.sens_label.setText(f"Mouse Aim Sensitivity: {val:.2f}")

    def _on_vol_changed(self):
        val = self.vol_slider["value"]
        USER_SETTINGS["audio_volume"] = val
        self.vol_label.setText(f"Master Audio Volume: {int(val * 100)}%")
        self.app.apply_audio_volume()

    def _on_fov_changed(self):
        val = self.fov_slider["value"]
        USER_SETTINGS["fov"] = val
        self.fov_label.setText(f"Camera Field of View: {int(val)} deg")
        self.app.camLens.setFov(val)

    def _toggle_weather(self):
        USER_SETTINGS["weather_enabled"] = not USER_SETTINGS["weather_enabled"]
        status = "ON" if USER_SETTINGS["weather_enabled"] else "OFF"
        self.weather_btn["text"] = f"ION STORM WEATHER: {status}"
        self.app.play_sfx("ui_click")

    def show_banner(self, text: str, duration: float = 3.5):
        self.banner_text.setText(text)
        self.banner_timer = duration

    def trigger_screen_flash(self, color: tuple, alpha: float = 0.38):
        self.flash_color = color
        self.flash_alpha = alpha

    def show_state(self, state: str):
        self.hud_root.hide()
        self.menu_root.hide()
        self.pause_root.hide()
        self.settings_root.hide()
        self.gameover_root.hide()

        if state == "PLAYING":
            self.hud_root.show()
        elif state == "MENU":
            self.menu_root.show()
        elif state == "PAUSED":
            self.pause_root.show()
        elif state == "SETTINGS":
            self.settings_root.show()
        elif state == "GAMEOVER":
            self.gameover_root.show()

    def update_hud(self, dt: float, player, sector_info: dict, relics_collected: int, relics_list: list, enemies_list: list, boss, score: int):
        # Update status bars
        hull_ratio = max(0.001, player.hull / PLAYER_MAX_HULL)
        shield_ratio = max(0.001, player.shield / PLAYER_MAX_SHIELD)
        energy_ratio = max(0.001, player.energy / PLAYER_MAX_ENERGY)

        self.hull_fill["frameSize"] = (0.0, 0.52 * hull_ratio, -0.014, 0.014)
        self.shield_fill["frameSize"] = (0.0, 0.52 * shield_ratio, -0.014, 0.014)
        self.energy_fill["frameSize"] = (0.0, 0.52 * energy_ratio, -0.014, 0.014)

        self.sector_text.setText(sector_info["name"].upper())
        hostiles = len(enemies_list) + (1 if (boss and boss.alive) else 0)
        self.objective_text.setText(
            f"Relics Extracted: {relics_collected} / {sector_info['relics_required']}   |   Hostiles Active: {hostiles}"
        )
        self.score_text.setText(f"SCORE: {score:06d}")

        # Boss health bar
        if boss and boss.alive:
            self.boss_bar_bg.show()
            b_ratio = max(0.001, boss.hp / boss.max_hp)
            self.boss_bar_fill["frameSize"] = (0.0, 0.90 * b_ratio, -0.018, 0.018)
        else:
            self.boss_bar_bg.hide()

        # Banner timer fade
        if self.banner_timer > 0.0:
            self.banner_timer -= dt
            if self.banner_timer <= 0.0:
                self.banner_text.setText("")

        # Screen flash decay
        if self.flash_alpha > 0.0:
            self.flash_alpha = max(0.0, self.flash_alpha - dt * 1.8)
            r, g, b = self.flash_color
            self.flash_frame["frameColor"] = (r, g, b, self.flash_alpha)

        # Update 2D Radar Blips rotated relative to Player heading
        for blip in self.radar_blips:
            blip.hide()

        rad_yaw = math.radians(-player.yaw)
        cos_a, sin_a = math.cos(rad_yaw), math.sin(rad_yaw)
        radar_range = 190.0
        blip_idx = 0

        # Draw Relic Blips (Cyan)
        for relic in relics_list:
            if not relic.alive or blip_idx >= len(self.radar_blips):
                continue
            dx = relic.base_pos.x - player.pos.x
            dy = relic.base_pos.y - player.pos.y
            rx = (dx * cos_a - dy * sin_a) / radar_range * self.radar_radius
            ry = (dx * sin_a + dy * cos_a) / radar_range * self.radar_radius
            rx = max(-self.radar_radius * 0.92, min(self.radar_radius * 0.92, rx))
            ry = max(-self.radar_radius * 0.92, min(self.radar_radius * 0.92, ry))
            blip = self.radar_blips[blip_idx]
            blip["frameColor"] = (0.15, 0.98, 0.85, 1.0)
            blip.setPos(rx, 0, ry)
            blip.show()
            blip_idx += 1

        # Draw Enemy Blips (Red / Orange)
        for enemy in enemies_list:
            if not enemy.alive or blip_idx >= len(self.radar_blips):
                continue
            dx = enemy.pos.x - player.pos.x
            dy = enemy.pos.y - player.pos.y
            rx = (dx * cos_a - dy * sin_a) / radar_range * self.radar_radius
            ry = (dx * sin_a + dy * cos_a) / radar_range * self.radar_radius
            rx = max(-self.radar_radius * 0.92, min(self.radar_radius * 0.92, rx))
            ry = max(-self.radar_radius * 0.92, min(self.radar_radius * 0.92, ry))
            blip = self.radar_blips[blip_idx]
            blip["frameColor"] = (1.0, 0.25, 0.30, 1.0)
            blip.setPos(rx, 0, ry)
            blip.show()
            blip_idx += 1

        # Draw Boss Blip (Large Magenta)
        if boss and boss.alive and blip_idx < len(self.radar_blips):
            dx = boss.pos.x - player.pos.x
            dy = boss.pos.y - player.pos.y
            rx = (dx * cos_a - dy * sin_a) / radar_range * self.radar_radius
            ry = (dx * sin_a + dy * cos_a) / radar_range * self.radar_radius
            rx = max(-self.radar_radius * 0.92, min(self.radar_radius * 0.92, rx))
            ry = max(-self.radar_radius * 0.92, min(self.radar_radius * 0.92, ry))
            blip = self.radar_blips[blip_idx]
            blip["frameColor"] = (1.0, 0.1, 0.85, 1.0)
            blip.setPos(rx, 0, ry)
            blip.show()