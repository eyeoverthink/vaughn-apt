"""Build a high-detail, modular, game-ready Blender 5.3 Escape Room level of the user's apartment,
textured with real cropped photos from IMG_6804.MOV & IMG_6805.MOV and aligned to the 3D scan.

Outputs:
  - blender/apartment_escape_room.blend  (self-contained editable Blender 5.3 scene)
  - exports/apartment_escape_room.glb    (glTF 2.0 for WebGL / Godot / Unity / Unreal)
  - exports/apartment_escape_room.fbx    (FBX for Unreal / Unity)
  - renders/preview_*.png                (5 EEVEE renders for visual verification)
"""
import math
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

PROJECT_DIR = Path(r"C:\Users\eyeov\.gemini\antigravity\scratch\apartment-world")
BLENDER_DIR = PROJECT_DIR / "blender"
EXPORTS_DIR = PROJECT_DIR / "exports"
RENDERS_DIR = PROJECT_DIR / "renders"
TEX_DIR = PROJECT_DIR / "textures"
SCAN_PLY = PROJECT_DIR / "scan" / "living_scan_aligned.ply"

for d in (BLENDER_DIR, EXPORTS_DIR, RENDERS_DIR):
    d.mkdir(parents=True, exist_ok=True)

H = 2.85
WALL_T = 0.14


# ---------------------------------------------------------------------------
# Helpers: Collections, Materials, Geometry
# ---------------------------------------------------------------------------
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def get_collection(name: str):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def link_to(obj, col_name: str):
    col = get_collection(col_name)
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def make_mat(name: str, color, roughness=0.5, metallic=0.0, emission=None, emission_strength=0.0, alpha=1.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color[:3], 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None and emission_strength > 0:
        bsdf.inputs["Emission Color"].default_value = (*emission[:3], 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        if hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
    return mat


def make_wood_mat(name: str, col1, col2, scale=6.0, roughness=0.36):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    tex_coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale * 0.16, scale)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4.0
    noise.inputs["Detail"].default_value = 9.0
    noise.inputs["Distortion"].default_value = 1.4
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (*col1, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (*col2, 1.0)
    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def make_granite_mat(name: str):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    tc = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 52.0
    noise.inputs["Detail"].default_value = 10.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.12, 0.12, 0.13, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.45, 0.44, 0.42, 1.0)
    links.new(tc.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.16
    return mat


def make_image_mat(name: str, img_path: Path, emissive=False, strength=1.15, roughness=0.75, tile=(1.0, 1.0)):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    tc = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (tile[0], tile[1], 1.0)
    tex = nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.load(str(img_path))
    img.pack()
    tex.image = img
    links.new(tc.outputs["UV"], mp.inputs["Vector"])
    links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    if emissive:
        links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def add_box(name, loc, size, col_name, mat=None, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        bpy.ops.object.modifier_apply(modifier=mod.name)
    if mat:
        obj.data.materials.append(mat)
    return link_to(obj, col_name)


def add_box_minmax(name, x0, x1, y0, y1, z0, z1, col_name, mat=None, bevel=0.0):
    return add_box(
        name,
        loc=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
        size=(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)),
        col_name=col_name,
        mat=mat,
        bevel=bevel,
    )


def add_textured_plane(name, loc, width, height, rot, col_name, mat):
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (width, height, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(mat)
    return link_to(obj, col_name)


def add_cyl(name, loc, radius, depth, col_name, mat=None, rot=(0, 0, 0), verts=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    return link_to(obj, col_name)


def add_door(name, hinge_x, hinge_y, width, height, axis, mat_door, mat_metal, mat_trim, col_name, open_deg=0.0, keypad=False):
    thick = 0.045
    mesh = bpy.data.meshes.new(name + "_Mesh")
    bm = bmesh.new()
    if axis == "X":
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(width, thick, height), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(width / 2, 0.0, height / 2), verts=bm.verts)
    else:
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(thick, width, height), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(0.0, width / 2, height / 2), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (hinge_x, hinge_y, 0.0)
    obj.rotation_euler = (0.0, 0.0, math.radians(open_deg))
    obj.data.materials.append(mat_door)
    link_to(obj, col_name)

    # Door casing/frame trim (static around opening)
    cw = 0.055
    if axis == "X":
        add_box(name + "_FrameL", (hinge_x - cw / 2, hinge_y, height / 2), (cw, 0.17, height), col_name, mat_trim)
        add_box(name + "_FrameR", (hinge_x + width + cw / 2, hinge_y, height / 2), (cw, 0.17, height), col_name, mat_trim)
        add_box(name + "_FrameT", (hinge_x + width / 2, hinge_y, height + cw / 2), (width + cw * 2, 0.17, cw), col_name, mat_trim)
    else:
        add_box(name + "_FrameL", (hinge_x, hinge_y - cw / 2, height / 2), (0.17, cw, height), col_name, mat_trim)
        add_box(name + "_FrameR", (hinge_x, hinge_y + width + cw / 2, height / 2), (0.17, cw, height), col_name, mat_trim)
        add_box(name + "_FrameT", (hinge_x, hinge_y + width / 2, height + cw / 2), (0.17, width + cw * 2, cw), col_name, mat_trim)

    hx = width - 0.10 if axis == "X" else 0.0
    hy = 0.0 if axis == "X" else width - 0.10
    handle = add_box(
        name + "_Handle",
        loc=(hinge_x + hx, hinge_y + hy, 0.98),
        size=(0.12 if axis == "X" else 0.14, 0.14 if axis == "X" else 0.12, 0.038),
        col_name=col_name,
        mat=mat_metal,
    )
    handle.parent = obj
    handle.matrix_parent_inverse = obj.matrix_world.inverted()

    if keypad:
        kp = add_box(
            name + "_SmartKeypad",
            loc=(hinge_x + hx, hinge_y + hy, 1.16),
            size=(0.075 if axis == "X" else 0.085, 0.085 if axis == "X" else 0.075, 0.18),
            col_name=col_name,
            mat=make_mat("Keypad_Glow", (0.04, 0.06, 0.09), 0.2, 0.4, (0.12, 0.78, 1.0), 2.2),
        )
        kp.parent = obj
        kp.matrix_parent_inverse = obj.matrix_world.inverted()
    return obj


def add_window_wall(name_prefix, x0, y0, x1, y1, sill_z, top_z, panels, col_name, mat_frame, mat_glass, mat_wall):
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    ang = math.atan2(dy, dx)
    if sill_z > 0.02:
        add_box(f"{name_prefix}_SillWall", ((x0 + x1) / 2, (y0 + y1) / 2, sill_z / 2), (length, WALL_T, sill_z), col_name, mat_wall, rot=(0, 0, ang))
    if H - top_z > 0.02:
        add_box(f"{name_prefix}_Header", ((x0 + x1) / 2, (y0 + y1) / 2, (top_z + H) / 2), (length, WALL_T, H - top_z), col_name, mat_wall, rot=(0, 0, ang))
    for hz, tag in [(sill_z + 0.03, "Bot"), (min(top_z - 0.35, 2.18), "Transom"), (top_z - 0.03, "Top")]:
        add_box(f"{name_prefix}_Rail_{tag}", ((x0 + x1) / 2, (y0 + y1) / 2, hz), (length, 0.075, 0.06), col_name, mat_frame, rot=(0, 0, ang))
    for i in range(panels + 1):
        t = i / panels
        add_box(f"{name_prefix}_Mullion_{i}", (x0 + dx * t, y0 + dy * t, (sill_z + top_z) / 2), (0.065, 0.085, top_z - sill_z), col_name, mat_frame, rot=(0, 0, ang))
    add_box(f"{name_prefix}_Glass", ((x0 + x1) / 2, (y0 + y1) / 2, (sill_z + top_z) / 2), (length - 0.06, 0.014, top_z - sill_z - 0.06), col_name, mat_glass, rot=(0, 0, ang))


def add_interact_marker(name, loc, label, col_name):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "SPHERE"
    empty.empty_display_size = 0.16
    empty.location = loc
    empty["escape_label"] = label
    return link_to(empty, col_name)


# ---------------------------------------------------------------------------
# Build the Upgraded Apartment
# ---------------------------------------------------------------------------
def build():
    clear_scene()

    # Core PBR Materials
    m_wall = make_mat("Wall_White", (0.90, 0.89, 0.86), 0.80)
    m_ceil = make_mat("Ceiling_White", (0.95, 0.95, 0.94), 0.85)
    m_trim = make_mat("Trim_White", (0.97, 0.97, 0.96), 0.38)
    m_floor_wood = make_wood_mat("Floor_OakPlank", (0.42, 0.31, 0.21), (0.58, 0.45, 0.33), scale=5.5, roughness=0.33)
    m_carpet = make_mat("Floor_OfficeCarpet", (0.60, 0.57, 0.53), 0.95)
    m_tile = make_mat("Floor_BathTile", (0.48, 0.45, 0.42), 0.38)
    m_mullion = make_mat("Window_Aluminum", (0.36, 0.38, 0.40), 0.32, 0.80)
    m_glass = make_mat("Window_Glass", (0.80, 0.90, 0.96), 0.04, 0.05, alpha=0.13)

    m_maple = make_wood_mat("Wood_MapleCabinet", (0.52, 0.27, 0.12), (0.69, 0.40, 0.18), scale=4.2, roughness=0.30)
    m_oak_door = make_wood_mat("Door_WarmOak", (0.58, 0.40, 0.20), (0.72, 0.53, 0.30), scale=3.2, roughness=0.36)
    m_dark_wood = make_wood_mat("Wood_DarkWalnut", (0.12, 0.09, 0.07), (0.20, 0.15, 0.11), scale=5.0, roughness=0.38)
    m_bistro_wood = make_wood_mat("Wood_BistroRound", (0.39, 0.19, 0.09), (0.54, 0.28, 0.13), scale=5.0, roughness=0.25)
    m_granite = make_granite_mat("Counter_Granite")

    m_stainless = make_mat("Metal_Stainless", (0.72, 0.74, 0.77), 0.22, 0.92)
    m_black_metal = make_mat("Metal_MatteBlack", (0.07, 0.07, 0.08), 0.38, 0.78)
    m_chrome = make_mat("Metal_Chrome", (0.86, 0.88, 0.90), 0.10, 0.96)

    m_cream_sofa = make_mat("Fabric_CreamSectional", (0.85, 0.82, 0.76), 0.88)
    m_pillow = make_mat("Fabric_ThrowPillow", (0.78, 0.74, 0.68), 0.90)
    m_blanket = make_mat("Fabric_DarkThrow", (0.12, 0.13, 0.15), 0.92)
    m_cognac = make_mat("Leather_Cognac", (0.48, 0.20, 0.10), 0.42)
    m_black_leather = make_mat("Leather_BlackChair", (0.06, 0.06, 0.07), 0.45)
    m_screen_off = make_mat("Screen_TV", (0.02, 0.02, 0.03), 0.10, 0.1)
    m_screen_glow = make_mat("Screen_MonitorGlow", (0.06, 0.11, 0.19), 0.14, 0.0, (0.20, 0.48, 0.88), 1.6)
    m_laptop_glow = make_mat("Screen_LaptopClue", (0.04, 0.18, 0.15), 0.12, 0.0, (0.12, 0.92, 0.68), 2.1)
    m_pendant_glow = make_mat("Light_PendantBulb", (1.0, 0.92, 0.76), 0.1, 0.0, (1.0, 0.88, 0.66), 4.8)
    m_can_glow = make_mat("Light_CanRecessed", (1.0, 0.96, 0.88), 0.1, 0.0, (1.0, 0.95, 0.86), 3.0)
    m_foil = make_mat("Window_FoilReflector", (0.76, 0.79, 0.82), 0.16, 0.94)
    m_red_accent = make_mat("Accent_Red", (0.58, 0.08, 0.08), 0.42)
    m_green_robe = make_mat("Fabric_GradRobe", (0.05, 0.22, 0.12), 0.82)
    m_gold = make_mat("Accent_Gold", (0.82, 0.64, 0.18), 0.30, 0.70)
    m_porcelain = make_mat("Bath_Porcelain", (0.95, 0.95, 0.94), 0.12)
    m_curtain = make_mat("Bath_GrayCurtain", (0.34, 0.36, 0.38), 0.85)
    m_bathmat = make_mat("Bath_BlueGrayMat", (0.34, 0.39, 0.44), 0.95)
    m_guitar_case = make_mat("Case_BrownGuitar", (0.30, 0.20, 0.15), 0.62)
    m_acoustic = make_mat("Wood_AcousticGuitar", (0.74, 0.52, 0.26), 0.22)
    m_blue_clue = make_mat("Clue_FilamentCyan", (0.08, 0.72, 0.98), 0.30, 0.0, (0.08, 0.74, 1.0), 1.6)
    m_uv_glow = make_mat("Clue_UVPurple", (0.55, 0.15, 0.98), 0.25, 0.0, (0.62, 0.20, 1.0), 2.4)
    m_led_green = make_mat("LED_MixerGreen", (0.10, 0.90, 0.38), 0.2, 0.0, (0.12, 0.95, 0.42), 2.2)
    m_cardboard = make_mat("Box_Cardboard", (0.56, 0.42, 0.26), 0.88)

    # Real Cropped Photo Materials from Your Apartment Videos!
    m_rug_real = (
        make_image_mat("Rug_RealJute", TEX_DIR / "tex_rug_clean.jpg", roughness=0.95, tile=(2.5, 3.2))
        if (TEX_DIR / "tex_rug_clean.jpg").exists()
        else make_wood_mat("Rug_Fallback", (0.56, 0.47, 0.36), (0.69, 0.60, 0.47), scale=26.0, roughness=0.95)
    )
    m_art_real = (
        make_image_mat("Art_RealTattooHands", TEX_DIR / "tex_wall_art_clean.jpg", roughness=0.55)
        if (TEX_DIR / "tex_wall_art_clean.jpg").exists()
        else m_trim
    )
    m_wb_real = (
        make_image_mat("Whiteboard_RealNotes", TEX_DIR / "tex_whiteboard_clean.jpg", roughness=0.16)
        if (TEX_DIR / "tex_whiteboard_clean.jpg").exists()
        else make_mat("Surface_Whiteboard", (0.95, 0.96, 0.97), 0.14)
    )
    m_vinyl_real = (
        make_image_mat("Vinyl_RealAlbum", TEX_DIR / "tex_vinyl_art.jpg", roughness=0.35)
        if (TEX_DIR / "tex_vinyl_art.jpg").exists()
        else m_red_accent
    )

    # =========================================================================
    # 01_ARCHITECTURE
    # =========================================================================
    C_ARCH = "01_Architecture"
    add_box_minmax("Floor_LivingKitchenDining", -3.9, 1.75, -2.05, 7.65, -0.10, 0.0, C_ARCH, m_floor_wood)
    add_box_minmax("Floor_EntryHallway", -0.35, 4.25, -3.95, -2.00, -0.10, 0.0, C_ARCH, m_floor_wood)
    add_box_minmax("Floor_MusicNook", 1.55, 2.35, 0.15, 2.05, -0.10, 0.0, C_ARCH, m_floor_wood)
    add_box_minmax("Floor_StudioOffice", -4.05, -0.30, -6.05, -2.05, -0.10, 0.0, C_ARCH, m_carpet)
    add_box_minmax("Floor_Bathroom", 1.25, 4.25, -6.05, -3.90, -0.10, 0.0, C_ARCH, m_tile)
    add_box_minmax("Ceiling_Main", -4.1, 4.3, -6.1, 7.7, H, H + 0.15, C_ARCH, m_ceil)

    # Solid Walls
    add_box_minmax("Wall_LivingEast_North", 1.60, 1.75, 3.95, 7.65, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_LivingEast_DoorHeader", 1.60, 1.75, 3.05, 3.95, 2.15, H, C_ARCH, m_wall)
    add_box_minmax("Wall_LivingEast_Whiteboard", 1.60, 1.75, 2.00, 3.05, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_MusicNook_Back", 2.30, 2.45, 0.15, 2.05, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_MusicNook_North", 1.60, 2.45, 1.98, 2.12, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_MusicNook_South", 1.60, 2.45, 0.08, 0.22, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_KitchenEast_North", 1.60, 1.75, -0.15, 0.22, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_KitchenEast_PantryHeader", 1.60, 1.75, -0.95, -0.15, 2.15, H, C_ARCH, m_wall)
    add_box_minmax("Wall_KitchenEast_Corner", 1.60, 1.75, -2.05, -0.95, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_EntryNorth", 1.60, 4.25, -2.08, -1.94, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_EntryEast_North", 4.15, 4.30, -2.55, -1.94, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_EntryEast_DoorHeader", 4.15, 4.30, -3.45, -2.55, 2.15, H, C_ARCH, m_wall)
    add_box_minmax("Wall_EntryEast_South", 4.15, 4.30, -4.00, -3.45, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_HallSouth_Left", -0.35, 2.05, -3.98, -3.84, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_HallSouth_BathHeader", 2.05, 2.85, -3.98, -3.84, 2.15, H, C_ARCH, m_wall)
    add_box_minmax("Wall_HallSouth_Right", 2.85, 4.30, -3.98, -3.84, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_BathWest", 1.20, 1.34, -6.05, -3.84, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_BathEast", 4.15, 4.30, -6.05, -3.84, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_BathSouth", 1.20, 4.30, -6.10, -5.96, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_KitchenSouth_StudioNorth", -4.05, -0.30, -2.14, -2.00, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_StudioEast_NorthHeader", -0.38, -0.24, -3.15, -2.25, 2.15, H, C_ARCH, m_wall)
    add_box_minmax("Wall_StudioEast_NorthPost", -0.38, -0.24, -2.25, -2.00, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_StudioEast_South", -0.38, -0.24, -6.05, -3.15, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_StudioCloset_Front", -1.45, -1.33, -6.05, -4.65, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_StudioCloset_Header", -1.45, -0.30, -4.75, -4.63, 2.15, H, C_ARCH, m_wall)
    add_box_minmax("Wall_West_KitchenCorner", -4.05, -3.85, -2.10, -1.15, 0, H, C_ARCH, m_wall)
    add_box_minmax("Wall_West_DiningArtPier", -4.05, -3.85, 0.35, 1.65, 0, H, C_ARCH, m_wall)

    # Crisp White Baseboards along key interior walls
    add_box_minmax("Baseboard_LivEast", 1.58, 1.60, 3.96, 7.55, 0.0, 0.10, C_ARCH, m_trim)
    add_box_minmax("Baseboard_LivWB", 1.58, 1.60, 2.02, 3.04, 0.0, 0.10, C_ARCH, m_trim)
    add_box_minmax("Baseboard_EntryNorth", 1.62, 4.15, -2.10, -2.08, 0.0, 0.10, C_ARCH, m_trim)
    add_box_minmax("Baseboard_HallSouth", -0.30, 2.04, -3.84, -3.82, 0.0, 0.10, C_ARCH, m_trim)
    add_box_minmax("Baseboard_StudioNorth", -3.90, -0.38, -2.16, -2.14, 0.0, 0.10, C_ARCH, m_trim)

    # Recessed Ceiling Downlights
    for idx, (lx, ly) in enumerate([
        (-2.2, 5.2), (0.2, 5.2), (-2.2, 2.2), (0.4, 2.2),
        (-2.2, -0.8), (0.4, -0.8), (2.2, -2.9), (-2.1, -3.8), (2.6, -5.0),
    ]):
        add_cyl(f"Ceiling_CanTrim_{idx+1}", (lx, ly, H - 0.008), 0.09, 0.016, C_ARCH, m_trim, verts=20)
        add_cyl(f"Ceiling_CanBulb_{idx+1}", (lx, ly, H - 0.012), 0.065, 0.012, C_ARCH, m_can_glow, verts=20)

    # Round White NW Corner Column
    add_cyl("Column_NWCorner", (-3.62, 7.32, H / 2), 0.27, H, C_ARCH, m_wall, verts=32)

    # =========================================================================
    # 02_WINDOWS_SKYLINE
    # =========================================================================
    C_WIN = "02_Windows_Skyline"
    add_window_wall("Win_LivingWest", -3.90, 1.65, -3.90, 7.55, 0.52, 2.70, 5, C_WIN, m_mullion, m_glass, m_wall)
    add_window_wall("Win_LivingNorth", -3.90, 7.55, 1.65, 7.55, 0.52, 2.70, 5, C_WIN, m_mullion, m_glass, m_wall)
    add_window_wall("Win_KitchenSink", -3.90, -1.15, -3.90, 0.35, 1.02, 2.45, 2, C_WIN, m_mullion, m_glass, m_wall)
    add_window_wall("Win_StudioWest", -3.95, -5.85, -3.95, -2.25, 0.55, 2.65, 3, C_WIN, m_mullion, m_glass, m_wall)
    add_window_wall("Win_StudioSouth", -3.95, -5.98, -1.45, -5.98, 0.55, 2.65, 2, C_WIN, m_mullion, m_glass, m_wall)

    sky_path = TEX_DIR / "skyline_clean.jpg"
    if sky_path.exists():
        m_sky = make_image_mat("Backdrop_RealSkyline", sky_path, emissive=True, strength=1.18)
        for tag, loc, w, h, rot_z in [
            ("Skyline_NorthView", (-1.0, 13.5, 2.1), 18.0, 11.0, 0.0),
            ("Skyline_WestView", (-10.0, 2.0, 2.1), 20.0, 11.0, math.pi / 2),
            ("Skyline_SouthView", (-2.5, -11.5, 2.1), 14.0, 10.0, math.pi),
        ]:
            add_textured_plane(tag, loc, w, h, (math.pi / 2, 0, rot_z), C_WIN, m_sky)

    # =========================================================================
    # 03_KITCHEN
    # =========================================================================
    C_KIT = "03_Kitchen"
    add_box_minmax("Kit_Cab_WestBase", -3.82, -3.15, -1.98, 0.72, 0.0, 0.88, C_KIT, m_maple)
    add_box_minmax("Kit_Cab_SouthBase", -3.15, -1.25, -1.98, -1.32, 0.0, 0.88, C_KIT, m_maple)
    add_box_minmax("Kit_Cab_PeninsulaBase", -3.15, -0.75, 0.08, 0.72, 0.0, 0.88, C_KIT, m_maple)
    # Peninsula cabinet pulls & kickplate
    add_box_minmax("Kit_Peninsula_Kickplate", -3.15, -0.78, 0.68, 0.74, 0.0, 0.09, C_KIT, m_dark_wood)
    for idx, px in enumerate([-2.80, -2.25, -1.70, -1.15]):
        add_box(f"Kit_PenPull_{idx+1}", (px, 0.735, 0.74), (0.14, 0.025, 0.016), C_KIT, m_chrome)
    add_box_minmax("Kit_Counter_West", -3.84, -3.12, -2.00, 0.78, 0.88, 0.92, C_KIT, m_granite, bevel=0.008)
    add_box_minmax("Kit_Counter_South", -3.15, -1.22, -2.00, -1.30, 0.88, 0.92, C_KIT, m_granite, bevel=0.008)
    add_box_minmax("Kit_Counter_Peninsula", -3.15, -0.68, 0.05, 0.92, 0.88, 0.92, C_KIT, m_granite, bevel=0.008)
    add_box_minmax("Kit_Peninsula_EndPanel", -0.78, -0.72, 0.06, 0.88, 0.0, 0.88, C_KIT, m_trim)
    add_box_minmax("Kit_Cab_UpperSouthLeft", -3.82, -2.62, -1.98, -1.62, 1.48, 2.38, C_KIT, m_maple)
    add_box_minmax("Kit_Cab_UpperSouthMid", -2.62, -1.82, -1.98, -1.62, 1.98, 2.38, C_KIT, m_maple)
    add_box_minmax("Kit_Cab_UpperSouthRight", -1.82, -1.25, -1.98, -1.62, 1.48, 2.38, C_KIT, m_maple)
    add_box_minmax("Kit_Cab_UpperWestCorner", -3.82, -3.45, 0.36, 0.78, 1.48, 2.38, C_KIT, m_maple)

    # Stainless Fridge, Range w/ Burners & Handle, Microwave w/ Display
    add_box_minmax("Kit_Fridge_Body", -1.22, -0.35, -1.98, -1.22, 0.0, 1.84, C_KIT, m_stainless, bevel=0.015)
    add_box_minmax("Kit_Fridge_HandleL", -0.82, -0.79, -1.22, -1.16, 0.95, 1.56, C_KIT, m_chrome)
    add_box_minmax("Kit_Fridge_HandleR", -0.76, -0.73, -1.22, -1.16, 0.95, 1.56, C_KIT, m_chrome)
    add_box_minmax("Kit_Range_Oven", -2.60, -1.84, -1.96, -1.28, 0.0, 0.91, C_KIT, m_stainless, bevel=0.01)
    add_box_minmax("Kit_Range_Window", -2.50, -1.94, -1.29, -1.27, 0.32, 0.68, C_KIT, m_screen_off)
    add_box_minmax("Kit_Range_Handle", -2.52, -1.92, -1.28, -1.22, 0.76, 0.79, C_KIT, m_chrome)
    add_box_minmax("Kit_Range_Cooktop", -2.58, -1.86, -1.92, -1.32, 0.91, 0.93, C_KIT, m_black_metal)
    for bx, by in [(-2.40, -1.48), (-2.04, -1.48), (-2.40, -1.76), (-2.04, -1.76)]:
        add_cyl(f"Kit_Burner_{bx:.1f}_{by:.1f}", (bx, by, 0.933), 0.09, 0.006, C_KIT, m_mullion, verts=20)
    add_box_minmax("Kit_Range_BackPanel", -2.60, -1.84, -1.96, -1.85, 0.91, 1.15, C_KIT, m_stainless)
    add_box_minmax("Kit_Microwave", -2.60, -1.84, -1.96, -1.56, 1.48, 1.95, C_KIT, m_stainless, bevel=0.01)
    add_box_minmax("Kit_Microwave_Window", -2.52, -2.02, -1.57, -1.55, 1.55, 1.88, C_KIT, m_screen_off)
    add_box_minmax("Kit_Microwave_Clock", -1.98, -1.87, -1.57, -1.55, 1.78, 1.86, C_KIT, m_led_green)

    # Sink, Curved Faucet, Dishwasher, Coffee Maker
    add_box_minmax("Kit_Sink_Basin", -3.72, -3.22, -0.82, -0.18, 0.89, 0.93, C_KIT, m_stainless)
    add_cyl("Kit_Faucet_Stem", (-3.74, -0.50, 1.05), 0.018, 0.26, C_KIT, m_chrome)
    add_cyl("Kit_Faucet_Spout", (-3.64, -0.50, 1.16), 0.014, 0.20, C_KIT, m_chrome, rot=(0, math.pi / 2, 0))
    add_box_minmax("Kit_Dishwasher", -3.14, -3.11, -0.05, 0.56, 0.06, 0.85, C_KIT, m_stainless)
    add_box_minmax("Kit_CoffeeMaker", -3.65, -3.38, 0.42, 0.66, 0.92, 1.24, C_KIT, m_black_metal, bevel=0.01)
    add_cyl("Kit_CoffeePot", (-3.45, 0.54, 1.01), 0.065, 0.14, C_KIT, m_glass)

    # Two Hanging Pendant Lights + Two Cognac Bar Stools
    for idx, px in enumerate([-2.45, -1.35]):
        add_cyl(f"Kit_PendantCord_{idx+1}", (px, 0.55, 2.35), 0.008, 1.0, C_KIT, m_chrome)
        add_cyl(f"Kit_PendantShade_{idx+1}", (px, 0.55, 1.80), 0.085, 0.18, C_KIT, m_pendant_glow)
    for idx, sx in enumerate([-2.35, -1.45]):
        add_cyl(f"Kit_StoolBase_{idx+1}", (sx, 1.12, 0.34), 0.03, 0.66, C_KIT, m_black_metal)
        add_cyl(f"Kit_StoolFoot_{idx+1}", (sx, 1.12, 0.02), 0.20, 0.03, C_KIT, m_black_metal)
        add_box(f"Kit_StoolSeat_{idx+1}", (sx, 1.12, 0.69), (0.42, 0.40, 0.07), C_KIT, m_cognac, bevel=0.02)
        add_box(f"Kit_StoolBack_{idx+1}", (sx, 1.30, 0.86), (0.42, 0.06, 0.30), C_KIT, m_cognac, bevel=0.02)

    # =========================================================================
    # 04_LIVINGROOM (Real Jute Rug Texture + Modular Cushions + Props!)
    # =========================================================================
    C_LIV = "04_LivingRoom"
    add_textured_plane("Liv_WovenRug", (-1.10, 4.65, 0.014), 3.10, 3.20, (0, 0, 0), C_LIV, m_rug_real)

    # Modular Cream Sectional Sofa (distinct cushions + throw pillows + dark blanket!)
    add_box_minmax("Liv_Sectional_WestFrame", -3.72, -2.68, 3.20, 6.45, 0.04, 0.28, C_LIV, m_cream_sofa, bevel=0.02)
    for idx, sy in enumerate([3.65, 4.50, 5.35, 6.08]):
        add_box(f"Liv_Sectional_CushionW_{idx+1}", (-3.16, sy, 0.38), (0.94, 0.80, 0.18), C_LIV, m_cream_sofa, bevel=0.05)
        add_box(f"Liv_Sectional_BackW_{idx+1}", (-3.58, sy, 0.68), (0.24, 0.78, 0.44), C_LIV, m_cream_sofa, bevel=0.06)
    add_box_minmax("Liv_Sectional_NorthFrame", -2.72, -1.55, 5.45, 6.50, 0.04, 0.28, C_LIV, m_cream_sofa, bevel=0.02)
    add_box("Liv_Sectional_CushionN", (-2.12, 5.95, 0.38), (1.12, 0.96, 0.18), C_LIV, m_cream_sofa, bevel=0.05)
    add_box("Liv_Sectional_BackN", (-2.12, 6.38, 0.68), (1.12, 0.24, 0.44), C_LIV, m_cream_sofa, bevel=0.06)
    add_box_minmax("Liv_Sectional_ArmSouth", -3.72, -2.68, 3.14, 3.34, 0.28, 0.66, C_LIV, m_cream_sofa, bevel=0.04)
    # Throw blanket & pillows
    add_box("Liv_ThrowBlanket", (-2.05, 5.85, 0.50), (0.62, 0.52, 0.06), C_LIV, m_blanket, rot=(0.04, 0.05, 0.22), bevel=0.02)
    add_box("Liv_Pillow1", (-3.36, 3.60, 0.58), (0.16, 0.42, 0.36), C_LIV, m_pillow, rot=(0, -0.22, 0.18), bevel=0.05)
    add_box("Liv_Pillow2", (-3.32, 6.08, 0.58), (0.38, 0.16, 0.36), C_LIV, m_pillow, rot=(0.22, 0, -0.65), bevel=0.05)
    # Red & white sneakers
    add_box("Liv_Sneaker_L", (-2.42, 3.58, 0.06), (0.11, 0.28, 0.11), C_LIV, m_red_accent, rot=(0, 0, 0.12), bevel=0.02)
    add_box("Liv_Sneaker_R", (-2.26, 3.60, 0.06), (0.11, 0.28, 0.11), C_LIV, m_red_accent, rot=(0, 0, -0.08), bevel=0.02)

    # Coffee Table + Backpack
    add_box_minmax("Liv_CoffeeTable_Top", -1.95, -0.85, 4.15, 4.95, 0.42, 0.46, C_LIV, m_dark_wood, bevel=0.008)
    for lx in (-1.90, -0.90):
        for ly in (4.20, 4.90):
            add_box(f"Liv_CTLeg_{lx:.1f}_{ly:.1f}", (lx, ly, 0.21), (0.04, 0.04, 0.42), C_LIV, m_black_metal)
    add_box("Liv_Backpack", (-1.42, 4.55, 0.58), (0.38, 0.45, 0.22), C_LIV, m_black_leather, rot=(0, 0, 0.2), bevel=0.05)

    # TV Console + Flat-Screen TV
    add_box_minmax("Liv_TVConsole_Top", 1.10, 1.56, 4.10, 5.75, 0.64, 0.68, C_LIV, m_dark_wood)
    add_box_minmax("Liv_TVConsole_Shelf", 1.12, 1.54, 4.12, 5.73, 0.22, 0.25, C_LIV, m_dark_wood)
    for ly in (4.14, 4.92, 5.70):
        add_box(f"Liv_TVLegL_{ly:.1f}", (1.13, ly, 0.34), (0.03, 0.03, 0.68), C_LIV, m_black_metal)
        add_box(f"Liv_TVLegR_{ly:.1f}", (1.53, ly, 0.34), (0.03, 0.03, 0.68), C_LIV, m_black_metal)
    add_box_minmax("Liv_TV_Screen", 1.32, 1.38, 4.25, 5.60, 0.78, 1.56, C_LIV, m_screen_off, bevel=0.005)
    add_box_minmax("Liv_TV_Stand", 1.24, 1.46, 4.78, 5.08, 0.68, 0.78, C_LIV, m_black_metal)

    # Acoustic Guitar by Corner Column
    add_box("Liv_AcousticGuitar_Body", (-3.15, 7.18, 0.28), (0.36, 0.12, 0.48), C_LIV, m_acoustic, rot=(0.18, 0, -0.3), bevel=0.05)
    add_cyl("Liv_AcousticGuitar_Hole", (-3.14, 7.12, 0.33), 0.055, 0.02, C_LIV, m_black_metal, rot=(math.pi / 2 + 0.18, 0, -0.3))
    add_box("Liv_AcousticGuitar_Neck", (-3.12, 7.25, 0.74), (0.055, 0.035, 0.50), C_LIV, m_dark_wood, rot=(0.18, 0, -0.3))

    # Bistro Table + Laptop + Windowsill Binoculars
    add_cyl("Liv_Bistro_Top", (-1.15, 7.02, 0.96), 0.34, 0.04, C_LIV, m_bistro_wood, verts=28)
    add_cyl("Liv_Bistro_Post", (-1.15, 7.02, 0.48), 0.035, 0.94, C_LIV, m_black_metal)
    add_cyl("Liv_Bistro_Base", (-1.15, 7.02, 0.02), 0.26, 0.03, C_LIV, m_black_metal)
    add_box("Liv_BistroLaptop_Base", (-1.15, 7.02, 0.995), (0.32, 0.22, 0.018), C_LIV, m_black_metal, rot=(0, 0, 0.25))
    add_box("Liv_BistroLaptop_Screen", (-1.18, 7.12, 1.10), (0.32, 0.015, 0.21), C_LIV, m_laptop_glow, rot=(-0.22, 0, 0.25))
    add_cyl("Liv_Binoculars_L", (-0.52, 7.42, 0.58), 0.028, 0.16, C_LIV, m_black_metal, rot=(math.pi / 2, 0, 0.15))
    add_cyl("Liv_Binoculars_R", (-0.45, 7.42, 0.58), 0.028, 0.16, C_LIV, m_black_metal, rot=(math.pi / 2, 0, 0.15))

    # Gaming & Ergo Chairs + NE Studio Desk
    for tag, cx, cy, rz in [("Liv_Chair_Ergo", -0.65, 6.45, 0.55), ("Liv_Chair_Gaming", 0.25, 6.55, -0.35)]:
        add_cyl(f"{tag}_Stem", (cx, cy, 0.24), 0.03, 0.44, C_LIV, m_black_metal)
        add_cyl(f"{tag}_Wheels", (cx, cy, 0.04), 0.30, 0.05, C_LIV, m_black_metal, verts=5)
        add_box(f"{tag}_Seat", (cx, cy, 0.48), (0.50, 0.48, 0.08), C_LIV, m_black_leather, rot=(0, 0, rz), bevel=0.02)
        add_box(f"{tag}_Back", (cx - 0.18 * math.cos(rz), cy - 0.18 * math.sin(rz), 0.90), (0.09, 0.46, 0.76), C_LIV, m_black_leather, rot=(0, 0, rz), bevel=0.03)
        for side in (-0.23, 0.23):
            add_box(f"{tag}_Arm_{'L' if side<0 else 'R'}", (cx - side * math.sin(rz), cy + side * math.cos(rz), 0.66), (0.30, 0.05, 0.04), C_LIV, m_black_metal, rot=(0, 0, rz))

    add_box_minmax("Liv_NEDesk_Top", 0.85, 1.56, 5.95, 7.35, 0.73, 0.77, C_LIV, m_trim)
    add_box_minmax("Liv_NEDesk_LegN", 0.88, 1.52, 7.26, 7.32, 0.0, 0.73, C_LIV, m_black_metal)
    add_box_minmax("Liv_NEDesk_LegS", 0.88, 1.52, 5.98, 6.04, 0.0, 0.73, C_LIV, m_black_metal)
    add_box_minmax("Liv_NEDesk_Monitor", 1.36, 1.41, 6.32, 6.96, 0.88, 1.24, C_LIV, m_screen_glow)
    for idx, sy in enumerate([6.02, 7.05]):
        add_box_minmax(f"Liv_NEDesk_Speaker{idx+1}", 1.25, 1.48, sy, sy + 0.20, 0.77, 1.04, C_LIV, m_black_metal)
        add_cyl(f"Liv_NEDesk_Cone{idx+1}", (1.24, sy + 0.10, 0.87), 0.06, 0.02, C_LIV, m_porcelain, rot=(0, math.pi / 2, 0))

    # =========================================================================
    # 05_MUSICNOOK_DINING (Real Framed Tattoo-Hands Art + Real Whiteboard + MIDI!)
    # =========================================================================
    C_MUS = "05_MusicNook_Dining"
    add_box_minmax("Din_Table_Top", -3.35, -2.15, 1.65, 2.55, 0.74, 0.78, C_MUS, m_dark_wood, bevel=0.01)
    for lx in (-3.30, -2.20):
        for ly in (1.70, 2.50):
            add_box(f"Din_TLeg_{lx:.1f}_{ly:.1f}", (lx, ly, 0.37), (0.05, 0.05, 0.74), C_MUS, m_dark_wood)
    for idx, (cx, cy, rz) in enumerate([(-2.75, 1.42, 0), (-2.75, 2.78, math.pi), (-1.92, 2.10, -math.pi / 2), (-3.55, 2.10, math.pi / 2)]):
        add_box(f"Din_ChairSeat_{idx+1}", (cx, cy, 0.45), (0.42, 0.42, 0.05), C_MUS, m_black_metal, rot=(0, 0, rz))
        add_box(f"Din_ChairBack_{idx+1}", (cx - 0.19 * math.sin(rz), cy - 0.19 * math.cos(rz), 0.72), (0.42, 0.04, 0.48), C_MUS, m_black_metal, rot=(0, 0, rz))
        for dx in (-0.18, 0.18):
            for dy in (-0.18, 0.18):
                add_box(f"Din_ChairLeg_{idx+1}_{dx:.1f}_{dy:.1f}", (cx + dx * math.cos(rz) - dy * math.sin(rz), cy + dx * math.sin(rz) + dy * math.cos(rz), 0.225), (0.03, 0.03, 0.45), C_MUS, m_black_metal)

    # Real Framed Wall Art on West Pier!
    add_box_minmax("Din_WallArt_FrameTop", -3.86, -3.83, 0.88, 1.42, 1.72, 2.34, C_MUS, m_black_metal)
    add_textured_plane("Din_WallArt_CanvasTop", (-3.825, 1.15, 2.03), 0.50, 0.58, (math.pi / 2, 0, math.pi / 2), C_MUS, m_art_real)
    add_box_minmax("Din_WallArt_Bot", -3.85, -3.82, 0.94, 1.36, 1.24, 1.64, C_MUS, m_trim)

    # Music Production Nook (61-Key MIDI w/ Black Keys, Mixer w/ Green LED, DJ Jog Wheels)
    add_box_minmax("Mus_Desk_Top", 1.68, 2.26, 0.25, 1.92, 0.74, 0.78, C_MUS, m_maple)
    add_box_minmax("Mus_Desk_LegN", 1.72, 2.22, 1.85, 1.90, 0.0, 0.74, C_MUS, m_black_metal)
    add_box_minmax("Mus_Desk_LegS", 1.72, 2.22, 0.28, 0.33, 0.0, 0.74, C_MUS, m_black_metal)
    add_box_minmax("Mus_MIDI_Body", 1.72, 2.10, 1.12, 1.94, 0.79, 0.87, C_MUS, m_black_metal, bevel=0.01)
    add_box_minmax("Mus_MIDI_WhiteKeys", 1.72, 1.86, 1.18, 1.88, 0.85, 0.88, C_MUS, m_porcelain)
    for k in range(12):
        if k % 7 not in (2, 6):
            add_box(f"Mus_MIDI_BlackKey_{k}", (1.82, 1.22 + k * 0.055, 0.885), (0.07, 0.018, 0.02), C_MUS, m_black_metal)
    add_box_minmax("Mus_DJController", 1.74, 2.08, 0.58, 1.04, 0.78, 0.84, C_MUS, m_black_metal)
    add_cyl("Mus_DJ_JogL", (1.90, 0.70, 0.845), 0.075, 0.015, C_MUS, m_chrome, verts=20)
    add_cyl("Mus_DJ_JogR", (1.90, 0.92, 0.845), 0.075, 0.015, C_MUS, m_chrome, verts=20)
    add_box_minmax("Mus_Mixer", 1.76, 2.16, 0.28, 0.54, 0.78, 0.85, C_MUS, m_stainless)
    add_box_minmax("Mus_Mixer_LED", 1.80, 1.90, 0.32, 0.50, 0.85, 0.86, C_MUS, m_led_green)
    for idx, sy in enumerate([0.48, 1.14]):
        add_box_minmax(f"Mus_MonitorBox_{idx+1}", 2.02, 2.24, sy, sy + 0.19, 0.78, 1.07, C_MUS, m_black_metal)
        add_cyl(f"Mus_MonitorCone_{idx+1}", (2.01, sy + 0.095, 0.88), 0.065, 0.02, C_MUS, m_porcelain, rot=(0, math.pi / 2, 0))
    add_cyl("Mus_MicStand", (1.65, 1.10, 0.65), 0.015, 1.30, C_MUS, m_black_metal)
    add_cyl("Mus_MicCapsule", (1.65, 1.10, 1.32), 0.026, 0.14, C_MUS, m_chrome)

    # Real Handwritten Whiteboard on East Wall!
    add_box_minmax("Mus_Whiteboard_Frame", 1.56, 1.60, 2.12, 2.98, 1.18, 1.84, C_MUS, m_mullion)
    add_textured_plane("Mus_Whiteboard_Surface", (1.555, 2.55, 1.51), 0.82, 0.62, (math.pi / 2, 0, -math.pi / 2), C_MUS, m_wb_real)

    # =========================================================================
    # 06_STUDIOOFFICE (Two Detailed 3D Printers + UV Clue Print + Foil + Desks)
    # =========================================================================
    C_OFF = "06_StudioOffice"
    for idx, fy in enumerate([-2.70, -3.35, -4.00]):
        add_box(f"Off_WindowFoil_{idx+1}", (-3.88, fy, 1.90), (0.015, 0.54, 0.88), C_OFF, m_foil)

    add_box_minmax("Off_WestDesk_Top", -3.82, -3.02, -5.15, -2.55, 0.73, 0.77, C_OFF, m_dark_wood)
    for dy in (-5.10, -3.85, -2.60):
        add_box(f"Off_WDeskLeg_{dy:.1f}", (-3.42, dy, 0.36), (0.74, 0.04, 0.73), C_OFF, m_black_metal)
    add_box_minmax("Off_Monitor_Low", -3.62, -3.57, -3.72, -3.02, 0.88, 1.28, C_OFF, m_screen_glow)
    add_box_minmax("Off_Monitor_High", -3.62, -3.57, -3.66, -3.08, 1.33, 1.68, C_OFF, m_screen_glow)
    add_box("Off_Keyboard", (-3.22, -3.35, 0.785), (0.16, 0.44, 0.025), C_OFF, m_black_metal)

    # TWO Detailed 3D Printers (gantry, heated bed, X-rail, extruder head, filament spool, glowing UV lens print!)
    for idx, py in enumerate([-4.15, -4.75]):
        add_box_minmax(f"Off_3DPrinter{idx+1}_Base", -3.72, -3.22, py - 0.22, py + 0.22, 0.77, 0.86, C_OFF, m_black_metal)
        add_box_minmax(f"Off_3DPrinter{idx+1}_Bed", -3.64, -3.30, py - 0.15, py + 0.15, 0.86, 0.885, C_OFF, m_mullion)
        add_box_minmax(f"Off_3DPrinter{idx+1}_GantryL", -3.50, -3.45, py - 0.20, py - 0.16, 0.86, 1.32, C_OFF, m_black_metal)
        add_box_minmax(f"Off_3DPrinter{idx+1}_GantryR", -3.50, -3.45, py + 0.16, py + 0.20, 0.86, 1.32, C_OFF, m_black_metal)
        add_box_minmax(f"Off_3DPrinter{idx+1}_TopBar", -3.50, -3.45, py - 0.20, py + 0.20, 1.29, 1.33, C_OFF, m_black_metal)
        add_box_minmax(f"Off_3DPrinter{idx+1}_XRail", -3.49, -3.46, py - 0.18, py + 0.18, 1.06, 1.09, C_OFF, m_chrome)
        add_box(f"Off_3DPrinter{idx+1}_Head", (-3.45, py, 1.04), (0.08, 0.08, 0.10), C_OFF, m_red_accent if idx == 0 else m_mullion)
        add_cyl(f"Off_3DPrinter{idx+1}_Spool", (-3.47, py, 1.43), 0.10, 0.06, C_OFF, m_blue_clue if idx == 0 else m_black_metal, rot=(0, math.pi / 2, 0))
    # Glowing UV Lens printed on Printer #1 bed!
    add_cyl("Off_3DPrinter1_UVLensPrint", (-3.47, -4.15, 0.90), 0.055, 0.025, C_OFF, m_uv_glow, verts=20)
    # Cardboard parts box on studio floor (visible in v1_0081!)
    add_box_minmax("Off_CardboardBox", -3.45, -2.92, -5.25, -4.72, 0.0, 0.42, C_OFF, m_cardboard)

    add_box("Off_Stool_Seat", (-2.65, -3.35, 0.52), (0.34, 0.48, 0.07), C_OFF, m_black_leather, bevel=0.02)
    add_box("Off_Stool_Base", (-2.65, -3.35, 0.25), (0.30, 0.42, 0.48), C_OFF, m_black_metal)
    add_box_minmax("Off_CubeShelf", -3.40, -1.85, -5.82, -5.44, 0.0, 0.74, C_OFF, m_trim)
    add_box_minmax("Off_TV_Screen", -3.15, -2.10, -5.66, -5.60, 0.84, 1.46, C_OFF, m_screen_off)
    add_box("Off_ElecGuitar", (-1.62, -5.58, 0.52), (0.30, 0.06, 0.95), C_OFF, m_cream_sofa, rot=(0.15, 0, 0.4))

    add_box_minmax("Off_EastDesk_Top", -1.12, -0.40, -4.45, -3.32, 0.73, 0.77, C_OFF, m_dark_wood)
    add_box_minmax("Off_EastDesk_LegN", -1.08, -0.44, -3.38, -3.33, 0.0, 0.73, C_OFF, m_dark_wood)
    add_box_minmax("Off_EastDesk_LegS", -1.08, -0.44, -4.43, -4.38, 0.0, 0.73, C_OFF, m_dark_wood)
    add_box_minmax("Off_EastMon1", -0.62, -0.58, -4.32, -3.88, 0.88, 1.18, C_OFF, m_screen_glow)
    add_box_minmax("Off_EastMon2", -0.62, -0.58, -3.82, -3.38, 0.88, 1.18, C_OFF, m_screen_glow)
    add_cyl("Off_ClosetRod", (-0.85, -5.35, 1.72), 0.015, 1.20, C_OFF, m_chrome, rot=(math.pi / 2, 0, 0))
    for idx, cy in enumerate([-5.75, -5.55, -5.35, -5.15, -4.95]):
        add_box(f"Off_Jacket_{idx+1}", (-0.85, cy, 1.32), (0.42, 0.09, 0.72), C_OFF, m_black_leather if idx % 2 == 0 else m_cream_sofa, bevel=0.02)

    # =========================================================================
    # 07_ENTRYHALL_BATH
    # =========================================================================
    C_ENT = "07_EntryHall_Bath"
    add_door("Door_FrontEntry", 4.18, -3.42, 0.88, 2.12, "Y", m_oak_door, m_chrome, m_trim, C_ENT, open_deg=0.0, keypad=True)
    add_door("Door_StudioOffice", -0.32, -3.14, 0.86, 2.12, "Y", m_trim, m_chrome, m_trim, C_ENT, open_deg=72.0)
    add_door("Door_Bathroom", 2.08, -3.90, 0.76, 2.12, "X", m_trim, m_chrome, m_trim, C_ENT, open_deg=-68.0)
    add_door("Door_LivingMaster", 1.65, 3.08, 0.84, 2.12, "Y", m_trim, m_chrome, m_trim, C_ENT, open_deg=25.0)
    add_door("Door_Pantry", 1.65, -0.94, 0.78, 2.12, "Y", m_trim, m_chrome, m_trim, C_ENT, open_deg=0.0)
    add_box_minmax("Door_LouveredCloset", -0.10, 0.72, -3.86, -3.82, 0.02, 2.12, C_ENT, m_trim)

    # Entryway Bench + Real Album Vinyls + Cube Shelf + Guitar Case + Rolling Cart + Grad Robe/Cap
    add_box_minmax("Ent_TuftedBench_Seat", 2.05, 3.35, -2.55, -2.08, 0.40, 0.54, C_ENT, m_cream_sofa, bevel=0.03)
    add_box_minmax("Ent_TuftedBench_ArmL", 2.05, 2.18, -2.55, -2.08, 0.54, 0.76, C_ENT, m_cream_sofa, bevel=0.03)
    add_box_minmax("Ent_TuftedBench_ArmR", 3.22, 3.35, -2.55, -2.08, 0.54, 0.76, C_ENT, m_cream_sofa, bevel=0.03)
    for bx in (2.10, 3.30):
        for by in (-2.50, -2.12):
            add_cyl(f"Ent_BenchLeg_{bx:.1f}_{by:.1f}", (bx, by, 0.20), 0.025, 0.40, C_ENT, m_dark_wood)
    add_box("Ent_VinylRecords", (2.42, -2.26, 0.68), (0.34, 0.03, 0.34), C_ENT, m_vinyl_real, rot=(-0.22, 0, 0.15))
    add_box_minmax("Ent_WhiteCubeShelf", 3.42, 3.98, -2.42, -2.08, 0.0, 0.78, C_ENT, m_trim)
    add_box("Ent_GuitarCase", (1.82, -2.28, 0.56), (0.38, 0.16, 1.12), C_ENT, m_guitar_case, rot=(0.08, 0, 0.25), bevel=0.04)
    add_box_minmax("Ent_RollingCart", 3.15, 3.72, -3.78, -3.38, 0.12, 0.58, C_ENT, m_red_accent, bevel=0.02)
    for wx in (3.20, 3.66):
        for wy in (-3.72, -3.44):
            add_cyl(f"Ent_CartWheel_{wx:.1f}_{wy:.1f}", (wx, wy, 0.06), 0.06, 0.04, C_ENT, m_black_metal, rot=(math.pi / 2, 0, 0))
    add_box_minmax("Ent_GradRobe", 0.92, 1.24, -3.84, -3.72, 0.48, 1.72, C_ENT, m_green_robe, bevel=0.03)
    add_box("Ent_GradCap", (1.08, -3.77, 1.84), (0.24, 0.04, 0.24), C_ENT, m_black_leather, rot=(0, 0.78, 0))
    add_box("Ent_GradTassel", (1.16, -3.74, 1.76), (0.02, 0.02, 0.18), C_ENT, m_gold)
    add_box_minmax("Ent_Pennant", 1.26, 1.56, -3.84, -3.81, 1.82, 2.26, C_ENT, m_gold)

    # Bathroom Fixtures (Vanity + Porcelain Sink + Mirror + Bath Mat + Toilet + Tub + Curtain)
    add_box_minmax("Bath_Vanity_Cab", 1.36, 1.92, -5.05, -4.10, 0.0, 0.82, C_ENT, m_maple)
    add_box_minmax("Bath_Vanity_Top", 1.35, 1.95, -5.08, -4.08, 0.82, 0.86, C_ENT, m_granite)
    add_cyl("Bath_SinkBowl", (1.68, -4.58, 0.855), 0.20, 0.04, C_ENT, m_porcelain)
    add_cyl("Bath_Faucet", (1.46, -4.58, 0.92), 0.016, 0.14, C_ENT, m_chrome)
    add_box_minmax("Bath_Mirror", 1.34, 1.37, -5.05, -4.10, 1.05, 2.10, C_ENT, m_chrome)
    add_box_minmax("Bath_Mat", 2.02, 2.75, -5.25, -4.20, 0.0, 0.015, C_ENT, m_bathmat)
    add_box_minmax("Bath_Toilet_Tank", 1.36, 1.56, -5.82, -5.36, 0.38, 0.82, C_ENT, m_porcelain, bevel=0.02)
    add_cyl("Bath_Toilet_Bowl", (1.68, -5.59, 0.21), 0.20, 0.42, C_ENT, m_porcelain)
    add_box_minmax("Bath_Tub", 3.25, 4.14, -5.94, -4.25, 0.0, 0.46, C_ENT, m_porcelain, bevel=0.03)
    add_box_minmax("Bath_Curtain", 3.24, 3.28, -5.92, -4.85, 0.35, 2.12, C_ENT, m_curtain)
    add_cyl("Bath_CurtainRod", (3.26, -5.10, 2.14), 0.015, 1.72, C_ENT, m_chrome, rot=(math.pi / 2, 0, 0))

    # =========================================================================
    # 08_ESCAPEROOM_INTERACTABLES
    # =========================================================================
    C_ESC = "08_EscapeRoom_Interactables"
    add_interact_marker("INTERACT_FrontDoor_Keypad", (4.10, -2.62, 1.18), "Yale Keypad Lock (4-Digit PIN)", C_ESC)
    add_interact_marker("INTERACT_BistroLaptop", (-1.15, 7.02, 1.15), "Skyline Bistro Laptop (Clue 1)", C_ESC)
    add_interact_marker("INTERACT_Binoculars", (-0.48, 7.38, 0.65), "Windowsill Binoculars (Skyline Sighting)", C_ESC)
    add_interact_marker("INTERACT_MusicConsole", (1.85, 1.45, 0.95), "Playable MIDI Synth Console (Clue 2)", C_ESC)
    add_interact_marker("INTERACT_3DPrinter", (-3.35, -4.15, 1.15), "Studio 3D Printer & UV Lens (Clue 3)", C_ESC)
    add_interact_marker("INTERACT_Whiteboard", (1.52, 2.55, 1.52), "UV-Ink Hallway Whiteboard (Clue 4)", C_ESC)
    add_interact_marker("INTERACT_CoffeeMaker", (-3.50, 0.54, 1.15), "Kitchen Coffee Maker", C_ESC)
    add_interact_marker("INTERACT_Microwave", (-2.22, -1.55, 1.72), "Kitchen Microwave Timer", C_ESC)

    # =========================================================================
    # 09_3DSCAN_REFERENCE
    # =========================================================================
    C_SCAN = "09_3DScan_Reference"
    if SCAN_PLY.exists():
        bpy.ops.wm.ply_import(filepath=str(SCAN_PLY))
        scan_obj = bpy.context.active_object
        scan_obj.name = "COLMAP_3DScan_LivingKitchen"
        link_to(scan_obj, C_SCAN)
        scan_obj.hide_render = True
        scan_obj.hide_viewport = True

    # =========================================================================
    # 10_LIGHTING_CAMERAS (Punchy Golden Afternoon Sun!)
    # =========================================================================
    C_LGT = "10_Lighting_Cameras"
    world = bpy.data.worlds.new("ApartmentWorld")
    bpy.context.scene.world = world
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.62, 0.77, 0.95, 1.0)
    bg.inputs["Strength"].default_value = 0.55

    sun_data = bpy.data.lights.new("Sun_Afternoon", type="SUN")
    sun_data.energy = 4.5
    sun_data.color = (1.0, 0.92, 0.78)
    sun_obj = bpy.data.objects.new("Sun_Afternoon", sun_data)
    sun_obj.rotation_euler = (math.radians(52), math.radians(14), math.radians(-128))
    link_to(sun_obj, C_LGT)

    for lname, loc, energy, size, col in [
        ("Light_Living", (-1.0, 5.0, 2.65), 95.0, 2.4, (1.0, 0.95, 0.88)),
        ("Light_Kitchen", (-2.0, -0.3, 2.60), 80.0, 1.6, (1.0, 0.92, 0.80)),
        ("Light_DiningMusic", (-0.5, 2.0, 2.65), 70.0, 1.6, (1.0, 0.94, 0.86)),
        ("Light_Studio", (-2.1, -3.9, 2.60), 85.0, 2.0, (0.95, 0.97, 1.0)),
        ("Light_EntryHall", (2.0, -2.9, 2.60), 65.0, 1.4, (1.0, 0.92, 0.82)),
        ("Light_Bathroom", (2.6, -5.0, 2.60), 55.0, 1.2, (0.95, 0.98, 1.0)),
    ]:
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        link_to(lo, C_LGT)

    def add_cam(name, loc, target, lens=24.0):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.clip_end = 100.0
        co = bpy.data.objects.new(name, cd)
        co.location = loc
        co.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        link_to(co, C_LGT)
        return co

    cam_living = add_cam("Cam_LivingRoom", (0.8, 1.7, 1.55), (-2.2, 6.2, 1.15), lens=20.0)
    cam_kitchen = add_cam("Cam_KitchenDining", (1.2, 3.6, 1.65), (-2.5, -1.2, 1.05), lens=22.0)
    cam_studio = add_cam("Cam_StudioOffice", (-1.15, -2.55, 1.55), (-3.2, -4.6, 1.05), lens=19.0)
    cam_entry = add_cam("Cam_EntryHall", (0.2, -2.9, 1.55), (4.1, -2.9, 1.15), lens=20.0)
    cam_top = add_cam("Cam_TopDownFloorplan", (0.1, 0.8, 22.0), (0.1, 0.8, 0.0), lens=24.0)

    scene = bpy.context.scene
    scene.camera = cam_living
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Punchy"
    except Exception:
        pass

    # Save .blend, Export .glb & .fbx, Render 5 previews
    blend_path = BLENDER_DIR / "apartment_escape_room.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"Saved Blender file: {blend_path}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        if C_SCAN in [c.name for c in obj.users_collection]:
            continue
        if obj.type in ("MESH", "EMPTY"):
            obj.select_set(True)

    glb_path = EXPORTS_DIR / "apartment_escape_room.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_extras=True,
        export_yup=True,
    )
    print(f"Exported GLB: {glb_path}")

    fbx_path = EXPORTS_DIR / "apartment_escape_room.fbx"
    bpy.ops.export_scene.fbx(
        filepath=str(fbx_path),
        use_selection=True,
        apply_scale_options="FBX_SCALE_ALL",
        path_mode="COPY",
        embed_textures=True,
    )
    print(f"Exported FBX: {fbx_path}")

    ceil_obj = bpy.data.objects.get("Ceiling_Main")
    for cam, fname, hide_ceil in [
        (cam_living, "preview_living.png", False),
        (cam_kitchen, "preview_kitchen.png", False),
        (cam_studio, "preview_studio.png", False),
        (cam_entry, "preview_entry.png", False),
        (cam_top, "preview_floorplan.png", True),
    ]:
        if ceil_obj:
            ceil_obj.hide_render = hide_ceil
        scene.camera = cam
        scene.render.filepath = str(RENDERS_DIR / fname)
        bpy.ops.render.render(write_still=True)
    if ceil_obj:
        ceil_obj.hide_render = False
    print("All 5 upgraded verification renders complete!")


if __name__ == "__main__":
    build()
