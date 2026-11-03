"""
config.py - Configuration constants, terrain math, and GLSL shaders
for Aether Vanguard: Eclipse of Hyperion.
"""

import math

# Window & Display Settings
WINDOW_TITLE = "Aether Vanguard: Eclipse of Hyperion"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
TARGET_FPS = 60

# World & Terrain Constants
WORLD_SIZE = 700.0
WORLD_HALF = WORLD_SIZE * 0.5
TERRAIN_RESOLUTION = 110
BOUNDARY_RADIUS = 310.0

# Gameplay & Physics Constants
PLAYER_MAX_HULL = 100.0
PLAYER_MAX_SHIELD = 100.0
PLAYER_MAX_ENERGY = 100.0
SHIELD_REGEN_RATE = 7.5
SHIELD_REGEN_DELAY = 3.0
ENERGY_REGEN_RATE = 18.0

PLAYER_ACCEL = 115.0
PLAYER_BOOST_MULT = 1.75
PLAYER_DRAG = 3.2
PLAYER_HOVER_HEIGHT = 8.5
PLAYER_FIRE_COOLDOWN = 0.07
PLAYER_NOVA_COST = 45.0
PLAYER_NOVA_COOLDOWN = 2.5

# Dynamic User Settings (Modifiable via Settings Menu)
USER_SETTINGS = {
    "mouse_sensitivity": 0.16,
    "fov": 68.0,
    "audio_volume": 0.75,
    "weather_enabled": True,
}

# Sector Progression Definitions
SECTORS = [
    {
        "name": "Sector 1: Crystalline Frontier",
        "subtitle": "Extract 3 Data Relics & Eliminate Patrol Drones",
        "relics_required": 3,
        "drone_count": 6,
        "elite_count": 1,
        "spawn_boss": False,
        "fog_color": (0.04, 0.07, 0.14),
        "ambient_color": (0.18, 0.24, 0.35),
        "sun_color": (0.95, 0.88, 0.75),
    },
    {
        "name": "Sector 2: Ion Tempest Basin",
        "subtitle": "Extract 4 Data Relics Amidst Heavy Sentinel Resistance",
        "relics_required": 4,
        "drone_count": 9,
        "elite_count": 3,
        "spawn_boss": False,
        "fog_color": (0.07, 0.04, 0.13),
        "ambient_color": (0.22, 0.15, 0.32),
        "sun_color": (0.75, 0.85, 1.0),
    },
    {
        "name": "Sector 3: Eclipse of Hyperion",
        "subtitle": "Extract 4 Relics & Destroy the Siege Dreadnought",
        "relics_required": 4,
        "drone_count": 8,
        "elite_count": 4,
        "spawn_boss": True,
        "fog_color": (0.12, 0.03, 0.06),
        "ambient_color": (0.30, 0.14, 0.18),
        "sun_color": (1.0, 0.65, 0.55),
    },
]


def sample_terrain_height(x: float, y: float) -> float:
    """
    Deterministic continuous mathematical heightmap used by both the 3D mesh
    builder and the real-time physics/AI elevation solver.
    """
    nx = x * 0.018
    ny = y * 0.018
    # Multi-octave trigonometric ridges
    h1 = math.sin(nx) * math.cos(ny) * 14.0
    h2 = math.sin(nx * 2.3 + 1.4) * math.sin(ny * 2.1 - 0.8) * 6.5
    h3 = math.cos(nx * 4.7 - ny * 3.9) * 2.2

    # Central basin flattening for combat arena readability
    dist_center = math.hypot(x, y)
    basin_factor = min(1.0, max(0.15, (dist_center - 35.0) / 120.0))

    # Outer rim mountains near boundary
    rim_boost = 0.0
    if dist_center > BOUNDARY_RADIUS - 40.0:
        rim_boost = ((dist_center - (BOUNDARY_RADIUS - 40.0)) / 40.0) ** 2 * 38.0

    return (h1 + h2 + h3) * basin_factor + rim_boost


def sample_terrain_normal(x: float, y: float) -> tuple:
    """Computes the surface normal at (x, y) via central differences."""
    eps = 0.75
    h_l = sample_terrain_height(x - eps, y)
    h_r = sample_terrain_height(x + eps, y)
    h_d = sample_terrain_height(x, y - eps)
    h_u = sample_terrain_height(x, y + eps)
    dx = (h_l - h_r) / (2.0 * eps)
    dy = (h_d - h_u) / (2.0 * eps)
    dz = 1.0
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    return (dx / length, dy / length, dz / length)


# Custom GLSL Shaders (OpenGL 2.1 / GLSL 120 for universal hardware compatibility)
MAIN_VERTEX_SHADER = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;

attribute vec4 p3d_Vertex;
attribute vec3 p3d_Normal;
attribute vec4 p3d_Color;
attribute vec2 p3d_MultiTexCoord0;

varying vec3 v_world_pos;
varying vec3 v_world_normal;
varying vec4 v_color;
varying vec2 v_uv;

void main() {
    vec4 world_pos = p3d_ModelMatrix * p3d_Vertex;
    v_world_pos = world_pos.xyz;
    v_world_normal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
    v_color = p3d_Color;
    v_uv = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
}
"""

MAIN_FRAGMENT_SHADER = """#version 120
uniform sampler2D p3d_Texture0;
uniform vec3 u_cam_pos;
uniform vec3 u_light_dir;
uniform vec3 u_sun_color;
uniform vec3 u_ambient_color;
uniform vec3 u_fog_color;
uniform float u_time;
uniform float u_lightning;

varying vec3 v_world_pos;
varying vec3 v_world_normal;
varying vec4 v_color;
varying vec2 v_uv;

void main() {
    vec3 N = normalize(v_world_normal);
    vec3 L = normalize(u_light_dir);
    vec3 V = normalize(u_cam_pos - v_world_pos);
    vec3 H = normalize(L + V);

    vec4 tex_sample = texture2D(p3d_Texture0, v_uv);
    vec3 base_albedo = v_color.rgb * mix(vec3(1.0), tex_sample.rgb, 0.65);

    // Half-Lambert wrapped diffuse lighting for rich 3D form definition
    float ndotl = max(dot(N, L), 0.0);
    float wrapped_diff = pow(ndotl * 0.65 + 0.35, 1.4);

    // Blinn-Phong Specular highlight
    float spec = pow(max(dot(N, H), 0.0), 36.0) * 0.55;

    // Sci-Fi Fresnel Rim Lighting
    float fresnel = pow(1.0 - max(dot(N, V), 0.0), 3.2);
    vec3 rim_color = mix(u_sun_color, vec3(0.2, 0.85, 1.0), 0.6) * fresnel * 0.48;

    // Subtle animated energy pulse on high-saturation emissive vertices
    float color_lum = max(v_color.r, max(v_color.g, v_color.b));
    float color_min = min(v_color.r, min(v_color.g, v_color.b));
    float saturation = color_lum - color_min;
    float pulse = 0.88 + 0.12 * sin(u_time * 4.5 + v_world_pos.x * 0.1);
    vec3 emissive = v_color.rgb * smoothstep(0.45, 0.85, saturation) * 0.55 * pulse;

    // Combine lighting
    vec3 lit_color = base_albedo * (u_ambient_color + u_sun_color * wrapped_diff)
                   + u_sun_color * spec
                   + rim_color
                   + emissive;

    // Dynamic storm lightning flash boost
    lit_color += vec3(0.45, 0.65, 1.0) * u_lightning * max(N.z, 0.2);

    // Exponential Distance + Altitude Atmospheric Fog
    float dist = length(u_cam_pos - v_world_pos);
    float fog_factor = 1.0 - exp(-pow(dist * 0.0036, 1.65));
    fog_factor = clamp(fog_factor, 0.0, 1.0);

    vec3 final_rgb = mix(lit_color, u_fog_color, fog_factor);
    gl_FragColor = vec4(final_rgb, v_color.a);
}
"""