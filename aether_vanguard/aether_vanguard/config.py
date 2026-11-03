"""
config.py - Cấu hình trò chơi, tham số thế giới và hàm sinh địa hình.
"""

import math

WINDOW_TITLE = "Aether Vanguard: Eclipse of Hyperion"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720

USER_SETTINGS = {
    "fov": 65.0,
    "mouse_sensitivity": 0.15,
    "audio_volume": 0.8,
    "weather_enabled": True,
}

PLAYER_MAX_HULL = 100.0
PLAYER_MAX_SHIELD = 100.0
PLAYER_MAX_ENERGY = 100.0
SHIELD_REGEN_RATE = 15.0
SHIELD_REGEN_DELAY = 3.0
ENERGY_REGEN_RATE = 20.0

PLAYER_ACCEL = 115.0
PLAYER_BOOST_MULT = 1.85
PLAYER_DRAG = 3.2
PLAYER_FIRE_COOLDOWN = 0.05
PLAYER_NOVA_COST = 45.0
PLAYER_NOVA_COOLDOWN = 6.0

BOUNDARY_RADIUS = 320.0
WORLD_SIZE = 640.0
TERRAIN_RESOLUTION = 64

def sample_terrain_height(x: float, y: float) -> float:
    """Hàm tạo độ cao địa hình dựa trên dao động sóng hình sin phức hợp."""
    dist_from_origin = math.hypot(x, y)
    if dist_from_origin > BOUNDARY_RADIUS + 50.0:
        return 120.0
    
    base = math.sin(x * 0.02) * math.cos(y * 0.02) * 14.0
    detail = math.sin(x * 0.08) * math.cos(y * 0.08) * 4.0
    crater = -abs(math.cos(math.hypot(x, y) * 0.05)) * 6.0
    return max(2.0, base + detail + crater + 12.0)

def sample_terrain_normal(x: float, y: float):
    """Tính toán vector pháp tuyến (normal) của địa hình tại tọa độ (x, y)."""
    eps = 1.0
    hL = sample_terrain_height(x - eps, y)
    hR = sample_terrain_height(x + eps, y)
    hD = sample_terrain_height(x, y - eps)
    hU = sample_terrain_height(x, y + eps)
    
    from panda3d.core import Vec3
    nx = hL - hR
    ny = hD - hU
    nz = 2.0 * eps
    normal = Vec3(nx, ny, nz)
    normal.normalize()
    return normal


def get_procedural_sector(index: int):
    """Tự động sinh thông số độ khó và cảnh quan cho vô hạn các Sector chơi liên tục hàng giờ."""
    themes = [
        {"name": f"Sector {index}: Crystalline Nebula", "subtitle": "Extract Data Relics & Neutralize Hostile Drones", 
         "fog_color": (0.05, 0.08, 0.15), "ambient_color": (0.2, 0.3, 0.5), "sun_color": (0.4, 0.8, 1.0)},
        {"name": f"Sector {index}: Crimson Asteroid Belt", "subtitle": "High-Density Threat Zone - Engage with Caution", 
         "fog_color": (0.15, 0.05, 0.05), "ambient_color": (0.5, 0.2, 0.2), "sun_color": (1.0, 0.4, 0.2)},
        {"name": f"Sector {index}: Void Deep Space", "subtitle": "Extreme Radiation & Elite Dreadnought Presence", 
         "fog_color": (0.08, 0.02, 0.12), "ambient_color": (0.3, 0.1, 0.4), "sun_color": (0.8, 0.3, 1.0)}
    ]
    
    theme = themes[index % len(themes)]
    
    return {
        "name": theme["name"],
        "subtitle": theme["subtitle"],
        "fog_color": theme["fog_color"],
        "ambient_color": theme["ambient_color"],
        "sun_color": theme["sun_color"],
        "relics_required": min(3 + index // 2, 8),
        "drone_count": min(6 + index * 2, 28),
        "elite_count": min(2 + index, 12),
        "spawn_boss": (index % 3 == 0)
    }

SECTORS = [get_procedural_sector(i) for i in range(10)]

MAIN_VERTEX_SHADER = """
#version 330 core
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec2 p3d_MultiTexCoord0;
out vec2 v_texcoord;
out vec3 v_normal;
out vec3 v_world_pos;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_texcoord = p3d_MultiTexCoord0;
    v_normal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
    v_world_pos = vec3(p3d_ModelMatrix * p3d_Vertex);
}
"""

MAIN_FRAGMENT_SHADER = """
#version 330 core
uniform sampler2D p3d_Texture0;
uniform vec3 u_light_dir;
uniform vec3 u_sun_color;
uniform vec3 u_ambient_color;
uniform vec3 u_fog_color;
uniform vec3 u_cam_pos;
uniform float u_time;
uniform float u_lightning;

in vec2 v_texcoord;
in vec3 v_normal;
in vec3 v_world_pos;
out vec4 frag_color;

void main() {
    vec4 tex_color = texture(p3d_Texture0, v_texcoord);
    vec3 N = normalize(v_normal);
    vec3 L = normalize(-u_light_dir);
    
    float diff = max(dot(N, L), 0.2);
    vec3 lighting = u_ambient_color + u_sun_color * diff;
    lighting += vec3(u_lightning * 0.8);

    vec3 final_rgb = tex_color.rgb * lighting;
    
    float dist = distance(v_world_pos, u_cam_pos);
    float fog_factor = clamp(exp(-pow(dist * 0.003, 1.5)), 0.0, 1.0);
    vec3 mixed_color = mix(u_fog_color, final_rgb, fog_factor);

    frag_color = vec4(mixed_color, tex_color.a);
}
"""