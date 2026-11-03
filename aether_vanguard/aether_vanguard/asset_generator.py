"""
asset_generator.py - Procedural 3D Mesh Builder, Texture Synthesizer,
and PCM WAV Audio Generator.
"""

import os
import math
import wave
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    Vec3,
    Texture,
    SamplerState,
)

from config import sample_terrain_height, sample_terrain_normal, WORLD_SIZE, TERRAIN_RESOLUTION


class AssetGenerator:
    """Generates and caches all textures and audio files on startup."""

    def __init__(self, base_dir: str = "assets"):
        self.base_dir = base_dir
        self.tex_dir = os.path.join(base_dir, "textures")
        self.audio_dir = os.path.join(base_dir, "audio")
        os.makedirs(self.tex_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)

    def ensure_all_assets(self):
        """Creates all procedural textures and sound files if not already cached."""
        self._generate_textures()
        self._generate_audio()

    # ------------------------------------------------------------------
    # TEXTURE SYNTHESIS (NumPy + Pillow)
    # ------------------------------------------------------------------
    def _generate_textures(self):
        hull_path = os.path.join(self.tex_dir, "hull_metallic.png")
        if not os.path.exists(hull_path):
            size = 512
            arr = np.zeros((size, size, 3), dtype=np.uint8)
            # Brushed metallic base
            y_idx, x_idx = np.mgrid[0:size, 0:size]
            noise = (np.sin(x_idx * 0.25) * np.cos(y_idx * 0.08) * 18 + 185).astype(np.uint8)
            arr[:, :, 0] = noise
            arr[:, :, 1] = np.clip(noise + 8, 0, 255)
            arr[:, :, 2] = np.clip(noise + 20, 0, 255)

            img = Image.fromarray(arr, mode="RGB")
            draw = ImageDraw.Draw(img)
            # Sci-fi armor panel lines and rivets
            for step in range(0, size, 64):
                draw.line([(step, 0), (step, size)], fill=(90, 105, 125), width=3)
                draw.line([(0, step), (size, step)], fill=(90, 105, 125), width=3)
                draw.line([(step + 3, 0), (step + 3, size)], fill=(230, 240, 255), width=1)
            for rx in range(32, size, 64):
                for ry in range(32, size, 64):
                    draw.rectangle([rx - 14, ry - 14, rx + 14, ry + 14], outline=(120, 165, 210), width=2)
            img.save(hull_path)

        terrain_path = os.path.join(self.tex_dir, "terrain_grid.png")
        if not os.path.exists(terrain_path):
            size = 512
            y_idx, x_idx = np.mgrid[0:size, 0:size]
            rock = (
                145
                + 28 * np.sin(x_idx * 0.09) * np.cos(y_idx * 0.09)
                + 16 * np.cos((x_idx + y_idx) * 0.21)
            ).astype(np.uint8)
            arr = np.stack([rock, rock, np.clip(rock + 15, 0, 255)], axis=-1)
            img = Image.fromarray(arr, mode="RGB")
            draw = ImageDraw.Draw(img)
            # Glowing topological grid overlay
            for step in range(0, size, 32):
                col = (180, 235, 255) if step % 128 == 0 else (115, 150, 180)
                w = 2 if step % 128 == 0 else 1
                draw.line([(step, 0), (step, size)], fill=col, width=w)
                draw.line([(0, step), (size, step)], fill=col, width=w)
            img.save(terrain_path)

        crystal_path = os.path.join(self.tex_dir, "crystal_surface.png")
        if not os.path.exists(crystal_path):
            size = 256
            y_idx, x_idx = np.mgrid[0:size, 0:size]
            facets = (180 + 65 * np.abs(np.sin((x_idx - y_idx) * 0.08))).astype(np.uint8)
            arr = np.stack([facets, np.clip(facets + 20, 0, 255), np.full_like(facets, 255)], axis=-1)
            Image.fromarray(arr, mode="RGB").save(crystal_path)

        particle_path = os.path.join(self.tex_dir, "particle_glow.png")
        if not os.path.exists(particle_path):
            size = 128
            y_idx, x_idx = np.mgrid[0:size, 0:size]
            cx, cy = size / 2.0, size / 2.0
            dist = np.sqrt((x_idx - cx) ** 2 + (y_idx - cy) ** 2) / (size / 2.0)
            alpha = np.clip((1.0 - dist) ** 2.2, 0.0, 1.0)
            rgb = np.clip((1.0 - dist * 0.5), 0.0, 1.0)
            rgba = np.zeros((size, size, 4), dtype=np.uint8)
            rgba[:, :, 0] = (rgb * 255).astype(np.uint8)
            rgba[:, :, 1] = (rgb * 255).astype(np.uint8)
            rgba[:, :, 2] = (rgb * 255).astype(np.uint8)
            rgba[:, :, 3] = (alpha * 255).astype(np.uint8)
            Image.fromarray(rgba, mode="RGBA").save(particle_path)

    # ------------------------------------------------------------------
    # AUDIO & MUSIC SYNTHESIS (NumPy + wave)
    # ------------------------------------------------------------------
    def _write_wav(self, filename: str, samples: np.ndarray, sample_rate: int = 44100):
        filepath = os.path.join(self.audio_dir, filename)
        if os.path.exists(filepath):
            return
        clipped = np.clip(samples, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)
        with wave.open(filepath, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())

    def _generate_audio(self):
        sr = 44100

        # 1. Synthwave Ambient Background Track (12-second seamless loop)
        bgm_file = os.path.join(self.audio_dir, "bgm_synth.wav")
        if not os.path.exists(bgm_file):
            duration = 12.0
            t = np.linspace(0, duration, int(sr * duration), endpoint=False)
            # Bass progression (A1 -> F1 -> C2 -> G1)
            bass_freqs = np.select(
                [t < 3.0, t < 6.0, t < 9.0, t >= 9.0],
                [55.0, 43.65, 65.41, 49.0],
            )
            pulse = 0.5 + 0.5 * np.sin(2 * np.pi * (8.0 / 3.0) * t)
            bass = (
                0.22 * np.sin(2 * np.pi * bass_freqs * t)
                + 0.12 * np.sign(np.sin(2 * np.pi * bass_freqs * t)) * 0.35
            ) * pulse

            # Atmospheric lush fifth pad
            pad = (
                0.10 * np.sin(2 * np.pi * bass_freqs * 2.0 * t)
                + 0.08 * np.sin(2 * np.pi * bass_freqs * 3.0 * t + np.sin(t * 1.5))
                + 0.06 * np.sin(2 * np.pi * bass_freqs * 4.0 * t)
            )

            # Sixteenth-note crystalline arpeggio
            arp_notes = [220.0, 261.63, 329.63, 392.0, 440.0, 392.0, 329.63, 261.63]
            step_len = duration / 48.0
            step_idx = (t / step_len).astype(int) % len(arp_notes)
            arp_freq = np.choose(step_idx, arp_notes)
            arp_env = np.exp(-((t % step_len) / step_len) * 4.5)
            arp = 0.11 * np.sin(2 * np.pi * arp_freq * t) * arp_env

            self._write_wav("bgm_synth.wav", bass + pad + arp, sr)

        # 2. Primary Laser Pulse
        t = np.linspace(0, 0.16, int(sr * 0.16), endpoint=False)
        freq = np.linspace(1150.0, 190.0, len(t))
        env = np.exp(-t * 22.0)
        laser = 0.45 * np.sin(2 * np.pi * np.cumsum(freq) / sr) * env
        self._write_wav("laser_shoot.wav", laser, sr)

        # 3. Secondary Nova / Plasma Shockwave
        t = np.linspace(0, 0.65, int(sr * 0.65), endpoint=False)
        freq = np.linspace(420.0, 55.0, len(t))
        env = np.exp(-t * 4.8)
        nova = (
            0.5 * np.sin(2 * np.pi * np.cumsum(freq) / sr)
            + 0.25 * np.sin(2 * np.pi * 90.0 * t)
        ) * env
        self._write_wav("plasma_blast.wav", nova, sr)

        # 4. Explosion Detonation
        t = np.linspace(0, 0.55, int(sr * 0.55), endpoint=False)
        rng = np.random.default_rng(42)
        noise = rng.uniform(-1.0, 1.0, len(t))
        sub = np.sin(2 * np.pi * np.linspace(130.0, 28.0, len(t)) * t)
        exp_wave = (0.55 * sub + 0.45 * noise) * np.exp(-t * 6.5)
        self._write_wav("explosion.wav", exp_wave, sr)

        # 5. Shield Hit Deflection
        t = np.linspace(0, 0.18, int(sr * 0.18), endpoint=False)
        hit = 0.4 * np.sin(2 * np.pi * 680.0 * t + 4.0 * np.sin(2 * np.pi * 110.0 * t)) * np.exp(-t * 18.0)
        self._write_wav("hit_shield.wav", hit, sr)

        # 6. Relic Extraction Chime
        t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
        f_chime = np.select([t < 0.15, t < 0.30, t >= 0.30], [523.25, 659.25, 783.99])
        chime = 0.40 * np.sin(2 * np.pi * f_chime * t) * np.exp(-t * 4.0)
        self._write_wav("relic_pickup.wav", chime, sr)

        # 7. UI Click
        t = np.linspace(0, 0.05, int(sr * 0.05), endpoint=False)
        click = 0.35 * np.sin(2 * np.pi * 1400.0 * t) * np.exp(-t * 65.0)
        self._write_wav("ui_click.wav", click, sr)


class MeshBuilder:
    """
    Low-level procedural mesh builder using Panda3D's GeomVertexData.
    Constructs faceted, multi-part 3D geometry with exact surface normals,
    vertex color channels, and UV coordinates.
    """

    def __init__(self, name: str = "procedural_mesh"):
        self.name = name
        self.vdata = GeomVertexData(name, GeomVertexFormat.getV3n3c4t2(), Geom.UHStatic)
        self.v_writer = GeomVertexWriter(self.vdata, "vertex")
        self.n_writer = GeomVertexWriter(self.vdata, "normal")
        self.c_writer = GeomVertexWriter(self.vdata, "color")
        self.t_writer = GeomVertexWriter(self.vdata, "texcoord")
        self.tris = GeomTriangles(Geom.UHStatic)
        self.v_count = 0

    def add_tri(self, p1, p2, p3, color, uv1=(0, 0), uv2=(1, 0), uv3=(0.5, 1)):
        v1 = Vec3(*p1)
        v2 = Vec3(*p2)
        v3 = Vec3(*p3)
        edge1 = v2 - v1
        edge2 = v3 - v1
        normal = edge1.cross(edge2)
        if normal.lengthSquared() > 1e-12:
            normal.normalize()
        else:
            normal = Vec3(0, 0, 1)

        idx = self.v_count
        for pt, uv in ((v1, uv1), (v2, uv2), (v3, uv3)):
            self.v_writer.addData3(pt)
            self.n_writer.addData3(normal)
            self.c_writer.addData4(*color)
            self.t_writer.addData2(*uv)
        self.tris.addVertices(idx, idx + 1, idx + 2)
        self.v_count += 3

    def add_quad(self, p1, p2, p3, p4, color, uv_scale=1.0):
        self.add_tri(p1, p2, p3, color, (0, 0), (uv_scale, 0), (uv_scale, uv_scale))
        self.add_tri(p1, p3, p4, color, (0, 0), (uv_scale, uv_scale), (0, uv_scale))

    def add_tapered_prism(
        self,
        center_bottom,
        center_top,
        rx_bot,
        ry_bot,
        rx_top,
        ry_top,
        sides: int,
        color,
        cap_ends: bool = True,
        twist_rad: float = 0.0,
    ):
        """Builds a multi-sided tapered or twisted 3D prism/fuselage section."""
        cb = Vec3(*center_bottom)
        ct = Vec3(*center_top)
        axis = ct - cb
        if axis.lengthSquared() < 1e-9:
            return
        axis_n = Vec3(axis)
        axis_n.normalize()

        # Orthonormal basis perpendicular to axis
        up_ref = Vec3(0, 0, 1) if abs(axis_n.z) < 0.9 else Vec3(1, 0, 0)
        right = axis_n.cross(up_ref)
        right.normalize()
        up = right.cross(axis_n)
        up.normalize()

        bot_ring = []
        top_ring = []
        for i in range(sides):
            ang_b = (2.0 * math.pi * i) / sides
            ang_t = ang_b + twist_rad
            pb = cb + right * (math.cos(ang_b) * rx_bot) + up * (math.sin(ang_b) * ry_bot)
            pt = ct + right * (math.cos(ang_t) * rx_top) + up * (math.sin(ang_t) * ry_top)
            bot_ring.append(pb)
            top_ring.append(pt)

        for i in range(sides):
            nxt = (i + 1) % sides
            self.add_quad(bot_ring[i], bot_ring[nxt], top_ring[nxt], top_ring[i], color)
            if cap_ends:
                if rx_bot > 1e-4 or ry_bot > 1e-4:
                    self.add_tri(cb, bot_ring[nxt], bot_ring[i], color)
                if rx_top > 1e-4 or ry_top > 1e-4:
                    self.add_tri(ct, top_ring[i], top_ring[nxt], color)

    def build_nodepath(self) -> NodePath:
        self.tris.closePrimitive()
        geom = Geom(self.vdata)
        geom.addPrimitive(self.tris)
        node = GeomNode(self.name)
        node.addGeom(geom)
        return NodePath(node)


class MeshFactory:
    """High-level factory constructing all game 3D models and terrain."""

    @staticmethod
    def create_terrain_nodepath(texture: Texture) -> NodePath:
        res = TERRAIN_RESOLUTION
        half = WORLD_SIZE * 0.5
        step = WORLD_SIZE / (res - 1)

        vdata = GeomVertexData("terrain", GeomVertexFormat.getV3n3c4t2(), Geom.UHStatic)
        v_writer = GeomVertexWriter(vdata, "vertex")
        n_writer = GeomVertexWriter(vdata, "normal")
        c_writer = GeomVertexWriter(vdata, "color")
        t_writer = GeomVertexWriter(vdata, "texcoord")

        for iy in range(res):
            y = -half + iy * step
            for ix in range(res):
                x = -half + ix * step
                z = sample_terrain_height(x, y)
                nx, ny, nz = sample_terrain_normal(x, y)

                v_writer.addData3(x, y, z)
                n_writer.addData3(nx, ny, nz)

                # Altitude and slope-driven vertex biome coloring
                alt_norm = max(0.0, min(1.0, (z + 18.0) / 42.0))
                slope = 1.0 - max(0.0, min(1.0, nz))
                r = 0.14 + 0.25 * alt_norm + 0.18 * slope
                g = 0.22 + 0.34 * alt_norm + 0.08 * slope
                b = 0.35 + 0.42 * alt_norm
                c_writer.addData4(r, g, b, 1.0)
                t_writer.addData2(ix * 0.45, iy * 0.45)

        tris = GeomTriangles(Geom.UHStatic)
        for iy in range(res - 1):
            row0 = iy * res
            row1 = (iy + 1) * res
            for ix in range(res - 1):
                i00 = row0 + ix
                i10 = row0 + ix + 1
                i01 = row1 + ix
                i11 = row1 + ix + 1
                tris.addVertices(i00, i10, i11)
                tris.addVertices(i00, i11, i01)
        tris.closePrimitive()

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("terrain_geom")
        node.addGeom(geom)
        np_terrain = NodePath(node)
        if texture:
            np_terrain.setTexture(texture)
        return np_terrain

    @staticmethod
    def create_player_ship(hull_tex: Texture) -> NodePath:
        """Builds the multi-part Vanguard Interceptor starfighter."""
        root = NodePath("PlayerShipRoot")
        mb = MeshBuilder("vanguard_hull")

        hull_primary = (0.78, 0.85, 0.96, 1.0)
        hull_dark = (0.25, 0.32, 0.44, 1.0)
        canopy_glow = (0.10, 0.92, 1.00, 1.0)
        thruster_glow = (0.15, 0.85, 1.00, 1.0)
        accent_gold = (1.00, 0.68, 0.18, 1.0)

        # Forward nose cone & main fuselage spine (oriented along +Y)
        mb.add_tapered_prism((0, 0.6, 0.0), (0, 3.8, -0.05), 0.72, 0.42, 0.04, 0.04, 8, hull_primary)
        mb.add_tapered_prism((0, -2.2, 0.0), (0, 0.6, 0.0), 0.92, 0.50, 0.72, 0.42, 8, hull_primary)

        # Armored cockpit canopy
        mb.add_tapered_prism((0, -0.5, 0.28), (0, 1.8, 0.14), 0.46, 0.32, 0.10, 0.08, 6, canopy_glow)

        # Swept delta wings (Left & Right)
        for sign in (-1.0, 1.0):
            # Main inner wing foil
            p1 = (sign * 0.65, 1.1, 0.0)
            p2 = (sign * 3.45, -1.5, -0.08)
            p3 = (sign * 3.15, -2.35, -0.08)
            p4 = (sign * 0.65, -1.9, 0.0)
            mb.add_tapered_prism(
                (sign * 0.65, -0.4, 0.0),
                (sign * 3.35, -1.8, -0.10),
                1.25,
                0.14,
                0.42,
                0.06,
                6,
                hull_primary,
            )
            # Forward wing stabilizer strake
            mb.add_tapered_prism(
                (sign * 0.55, 0.4, 0.02),
                (sign * 1.85, -0.6, 0.0),
                0.85,
                0.10,
                0.28,
                0.05,
                4,
                accent_gold,
            )
            # Angled twin tail fins
            mb.add_tapered_prism(
                (sign * 0.75, -1.6, 0.18),
                (sign * 1.25, -2.4, 0.95),
                0.55,
                0.08,
                0.22,
                0.04,
                4,
                hull_dark,
            )
            # Dual engine nacelles & glowing plasma afterburners
            mb.add_tapered_prism(
                (sign * 0.85, -2.5, -0.02),
                (sign * 0.85, -0.3, -0.02),
                0.34,
                0.34,
                0.28,
                0.28,
                8,
                hull_dark,
            )
            mb.add_tapered_prism(
                (sign * 0.85, -2.75, -0.02),
                (sign * 0.85, -2.48, -0.02),
                0.24,
                0.24,
                0.31,
                0.31,
                8,
                thruster_glow,
            )
            # Wingtip pulse laser cannons
            mb.add_tapered_prism(
                (sign * 3.15, -1.9, -0.10),
                (sign * 3.15, 0.45, -0.10),
                0.10,
                0.10,
                0.05,
                0.05,
                6,
                canopy_glow,
            )

        hull_np = mb.build_nodepath()
        if hull_tex:
            hull_np.setTexture(hull_tex)
        hull_np.reparentTo(root)
        return root

    @staticmethod
    def create_enemy_drone(hull_tex: Texture, elite: bool = False) -> tuple:
        """
        Builds an articulated Hunter-Seeker Sentinel Drone with an independent
        rotating gyro-ring NodePath for smooth mechanical animation.
        """
        root = NodePath("EnemyDroneRoot")
        core_mb = MeshBuilder("drone_core")

        armor_col = (0.85, 0.22, 0.28, 1.0) if elite else (0.38, 0.42, 0.52, 1.0)
        eye_col = (1.0, 0.15, 0.35, 1.0) if elite else (1.0, 0.42, 0.10, 1.0)
        dark_metal = (0.18, 0.20, 0.26, 1.0)

        # Central polyhedral armored core
        core_mb.add_tapered_prism((0, 0, -1.1), (0, 0, 0.0), 0.25, 0.25, 1.35, 1.35, 8, armor_col)
        core_mb.add_tapered_prism((0, 0, 0.0), (0, 0, 1.1), 1.35, 1.35, 0.25, 0.25, 8, armor_col)

        # Forward glowing optic sensor lens
        core_mb.add_tapered_prism((0, 0.9, 0.0), (0, 1.55, 0.0), 0.52, 0.52, 0.18, 0.18, 8, eye_col)

        # Underside twin blaster barrels
        for sign in (-1.0, 1.0):
            core_mb.add_tapered_prism(
                (sign * 0.75, -0.4, -0.65),
                (sign * 0.75, 1.4, -0.65),
                0.14,
                0.14,
                0.08,
                0.08,
                6,
                dark_metal,
            )

        core_np = core_mb.build_nodepath()
        if hull_tex:
            core_np.setTexture(hull_tex)
        core_np.reparentTo(root)

        # Articulated outer gyro stabilizer ring
        ring_mb = MeshBuilder("drone_gyro_ring")
        segments = 10
        radius = 2.05 if elite else 1.75
        for i in range(segments):
            a0 = (2.0 * math.pi * i) / segments
            a1 = (2.0 * math.pi * (i + 1)) / segments
            p0 = (math.cos(a0) * radius, math.sin(a0) * radius, 0.0)
            p1 = (math.cos(a1) * radius, math.sin(a1) * radius, 0.0)
            col = eye_col if i % 2 == 0 else dark_metal
            ring_mb.add_tapered_prism(p0, p1, 0.18, 0.26, 0.18, 0.26, 4, col, cap_ends=False)

        ring_np = ring_mb.build_nodepath()
        if hull_tex:
            ring_np.setTexture(hull_tex)
        ring_np.reparentTo(root)
        if elite:
            root.setScale(1.32)

        return root, ring_np

    @staticmethod
    def create_boss_dreadnought(hull_tex: Texture) -> tuple:
        """Builds the Sector 3 Siege Dreadnought Boss with rotating shield pylons."""
        root = NodePath("BossDreadnought")
        mb = MeshBuilder("boss_hull")

        citadel_col = (0.28, 0.22, 0.35, 1.0)
        crimson_glow = (1.0, 0.12, 0.28, 1.0)
        gold_trim = (0.95, 0.72, 0.22, 1.0)

        # Massive tiered command citadel
        mb.add_tapered_prism((0, -8.0, 0), (0, 8.0, 0), 4.2, 2.4, 2.2, 1.2, 8, citadel_col)
        mb.add_tapered_prism((0, -4.0, 1.8), (0, 3.5, 1.8), 2.5, 1.6, 1.2, 0.9, 6, gold_trim)
        # Central reactor core spire
        mb.add_tapered_prism((0, 0, -3.5), (0, 0, 4.8), 1.6, 1.6, 0.4, 0.4, 8, crimson_glow)

        hull_np = mb.build_nodepath()
        if hull_tex:
            hull_np.setTexture(hull_tex)
        hull_np.reparentTo(root)

        # Orbiting shield generator pylon assembly
        pylon_mb = MeshBuilder("boss_pylons")
        for i in range(4):
            ang = i * (math.pi * 0.5)
            px = math.cos(ang) * 7.2
            py = math.sin(ang) * 7.2
            pylon_mb.add_tapered_prism((px, py, -3.2), (px, py, 3.2), 0.85, 0.85, 0.35, 0.35, 6, crimson_glow)
            pylon_mb.add_tapered_prism((0, 0, 0), (px, py, 0), 0.35, 0.35, 0.35, 0.35, 4, gold_trim)

        pylon_np = pylon_mb.build_nodepath()
        if hull_tex:
            pylon_np.setTexture(hull_tex)
        pylon_np.reparentTo(root)

        return root, pylon_np

    @staticmethod
    def create_relic_monolith(crystal_tex: Texture) -> tuple:
        """Builds an interactive Data Relic Obelisk with counter-rotating rings."""
        root = NodePath("RelicMonolith")
        mb = MeshBuilder("relic_core")

        cyan_glow = (0.12, 0.95, 0.88, 1.0)
        gold_ring = (1.0, 0.82, 0.25, 1.0)

        # Twisted floating crystal obelisk
        mb.add_tapered_prism((0, 0, -2.2), (0, 0, 0.0), 0.15, 0.15, 1.05, 1.05, 6, cyan_glow, twist_rad=0.5)
        mb.add_tapered_prism((0, 0, 0.0), (0, 0, 2.6), 1.05, 1.05, 0.08, 0.08, 6, cyan_glow, twist_rad=0.5)

        core_np = mb.build_nodepath()
        if crystal_tex:
            core_np.setTexture(crystal_tex)
        core_np.reparentTo(root)

        # Containment ring
        ring_mb = MeshBuilder("relic_ring")
        segs = 12
        rad = 1.95
        for i in range(segs):
            a0 = (2.0 * math.pi * i) / segs
            a1 = (2.0 * math.pi * (i + 1)) / segs
            p0 = (math.cos(a0) * rad, math.sin(a0) * rad, 0.0)
            p1 = (math.cos(a1) * rad, math.sin(a1) * rad, 0.0)
            ring_mb.add_tapered_prism(p0, p1, 0.14, 0.14, 0.14, 0.14, 4, gold_ring, cap_ends=False)

        ring_np = ring_mb.build_nodepath()
        if crystal_tex:
            ring_np.setTexture(crystal_tex)
        ring_np.reparentTo(root)

        return root, ring_np

    @staticmethod
    def create_crystal_cluster(crystal_tex: Texture, seed: int = 0) -> NodePath:
        """Builds environmental crystal spire formations for depth and cover."""
        rng = random.Random(seed)
        mb = MeshBuilder(f"crystal_cluster_{seed}")

        palette = [
            (0.15, 0.78, 0.98, 1.0),
            (0.55, 0.28, 0.95, 1.0),
            (0.18, 0.92, 0.72, 1.0),
        ]
        base_col = palette[seed % len(palette)]

        spire_count = rng.randint(3, 5)
        for _ in range(spire_count):
            ox = rng.uniform(-1.2, 1.2)
            oy = rng.uniform(-1.2, 1.2)
            tx = ox + rng.uniform(-2.2, 2.2)
            ty = oy + rng.uniform(-2.2, 2.2)
            height = rng.uniform(5.5, 14.5)
            r_base = rng.uniform(0.85, 1.85)
            mb.add_tapered_prism(
                (ox, oy, -1.0),
                (tx, ty, height),
                r_base,
                r_base,
                0.08,
                0.08,
                6,
                base_col,
                twist_rad=0.35,
            )

        np_cluster = mb.build_nodepath()
        if crystal_tex:
            np_cluster.setTexture(crystal_tex)
        return np_cluster