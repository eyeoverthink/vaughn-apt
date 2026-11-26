# vaughn-apt

**Hybrid 3D Video Reconstruction, Modular Blender 5.3 Escape-Room Level, Game-Engine Exports, Playable Three.js First-Person Walkthrough, and RTX 5070 3D Gaussian Splat (3DGS)** — built directly from two smartphone apartment walkthrough videos (`IMG_6804.MOV` & `IMG_6805.MOV`).

![Top-Down Apartment Floorplan Render](renders/preview_floorplan.png)

---

## Spatial Home OS & Cyber-Physical Reality Twin (Next Evolution)

Beyond the Escape Room and 3D Gaussian Splat, `vaughn-apt` is evolving into a **Spatial Home OS & Cyber-Physical Reality Twin** — uniting your **digital files**, **physical hardware inventory** (Arduinos, Basys FPGAs, Raspberry Pis, ICs, sensors, 10× 3D printers, music gear), **smart home devices**, **AI agents**, and **guests** inside one shared `apt://` spatial address space.

👉 **Read the full vision, `home_graph.json` schema, and 5-phase execution roadmap:** [**`docs/REALITY_OS_ARCHITECTURE.md`**](docs/REALITY_OS_ARCHITECTURE.md)

| Phase | Milestone | Status |
| :--- | :--- | :--- |
| **Phase 0** | 3D Video Reconstruction, Crisp 25k-step 3DGS, Modular Blender 5.3 Level, `.glb`/`.fbx`, Escape Room | ✅ Complete |
| **Phase 1** | Spatial Home OS MVP (`data/home_graph.json`, `scripts/home_os_server.py`, `web/home_os.html` — unified `apt://` shelf/drawer/closet atoms + bits, natural-language command & BOM search, fly-to spotlight, Owner/Guest privacy view, Living Room TV, persistent Stereo, live Whiteboard) | ✅ Complete |
| **Phase 2** | Local Filesystem Bridge & Vision Photo-to-Inventory Drawer Capture | ⏳ Planned |
| **Phase 3** | Cyber-Physical Hardware Bridge (3D Printer Farm, Smart Lamps / MQTT, WLED Pick-to-Light, Raspberry Pis) | ⏳ Planned |
| **Phase 4** | Room-Aware AI Agent & BOM Feasibility Planner | ⏳ Planned |
| **Phase 5** | "Guests" (Front Door Comms Concierge, Multiplayer Co-Presence, Per-Room Privacy) | ⏳ Planned |

---

## Visual Tour (Blender 5.3 EEVEE Renders)

| Corner Living Room & Stitched City Skyline | U-Shaped Kitchen, Dining & Real Framed Art |
| :---: | :---: |
| ![Corner Living Room](renders/preview_living.png) | ![Kitchen and Dining](renders/preview_kitchen.png) |

| Studio / 3D-Printer Office & Foil Windows | Entry Hallway, Yale Keypad & Bathroom |
| :---: | :---: |
| ![Studio Office](renders/preview_studio.png) | ![Entry Hallway](renders/preview_entry.png) |

---

## Project Architecture & Pipeline

This project takes raw handheld video and turns it into **four synchronized 3D deliverables** on a local Windows GPU workstation (**NVIDIA RTX 5070 12 GB**, **Blender 5.3**, **FFmpeg**, **pycolmap 4.2.1**, **Brush 3DGS**):

```
IMG_6804.MOV (85s) + IMG_6805.MOV (39s)
        │
        ▼  1. Frame Extraction & Sharpness Filtering (FFmpeg + OpenCV Laplacian)
  496 candidate frames ──► Sharp blur-filtered keyframes + real cropped apartment textures
        │
        ├──► 2A. Structure-from-Motion (pycolmap 4.2.1)
        │         ├─► Gravity-aligned 3D point cloud (living_scan_aligned.ply / living_scan_threejs.json)
        │         ├─► Floorplan & elevation measurements (8.2 m × 13.6 m, ~85 m²)
        │         └─► Brush 3D Gaussian Splatting (RTX 5070 WebGPU) ──► scan/splat/apartment_splat.ply
        │
        └──► 2B. Modular Blender 5.3 Level Generator (scripts/build_apartment_blender.py)
                  ├─► blender/apartment_escape_room.blend   (10 collections, 386 meshes, 45 materials)
                  ├─► exports/apartment_escape_room.glb     (glTF 2.0 w/ 5 embedded apartment textures)
                  ├─► exports/apartment_escape_room.fbx     (FBX w/ embedded textures for Unity/Unreal)
                  └─► web/                                  (Three.js Escape Room + 3DGS Splat Viewer)
```

### Real Cropped Apartment Textures Embedded in the 3D World
Rather than generic placeholders, key hero surfaces were cropped and rectified directly from the source videos and packed into both `.blend` and `.glb`:
- **Panoramic Downtown Skyline** (`textures/skyline_clean.jpg`) — OpenCV panorama stitched from 9 window-pan frames of `IMG_6805.MOV`
- **Woven Jute Living Room Rug** (`textures/tex_rug_clean.jpg`) — shadow-free seamlessly mirror-tiled weave
- **Framed Tattooed-Hands Painting** (`textures/tex_wall_art_clean.jpg`) — real canvas mounted on the dining pier wall
- **Handwritten Hallway Whiteboard** (`textures/tex_whiteboard_clean.jpg`) — real dry-erase notes mounted outside the Music Nook
- **Entryway Vinyl Album Art** (`textures/tex_vinyl_art.jpg`) — leaning on the tufted entryway bench

---

## 3D Reconstruction & Gaussian Splatting (3DGS)

### Structure-from-Motion Floorplan Analysis
`pycolmap 4.2.1` registered **187 / 191** sharp frames across the apartment zones, stitching both videos together across the living room, dining area, music nook, and kitchen, plus recovering the studio office and entry hallway:

| Living/Kitchen SfM Floorplan & Elevation | Multi-Zone Room Comparison |
| :---: | :---: |
| ![SfM Floorplan](scan/floorplan_analysis.png) | ![Room Zone Comparison](scan/rooms_floorplan_comparison.png) |

### 3D Gaussian Splat (Brush on RTX 5070) — v1 vs v2 Fix

The initial v1 splat was blurry and hazy because it trained for only 8,000 steps on 98 sparse `SIMPLE_RADIAL` (distorted) frames. For **v2**, the entire 3DGS pipeline was rebuilt from the ground up:

| Metric | v1 Baseline (Blurry) | v2 Fixed (Crisp) |
| :--- | :--- | :--- |
| **Registered Views** | 98 frames (2 fps, mixed) | **209 ultra-sharp frames** (4 fps, Laplacian ≥ 111.8) |
| **Camera Model** | `SIMPLE_RADIAL` (un-rectified) | **Exact `PINHOLE`** via `pycolmap.undistort_images` |
| **Initial 3D SfM Points** | 14,246 pts (2,500 SIFT/img) | **60,743 pts** (4,096 SIFT/img — **4.3× denser**) |
| **Training Steps / Res** | 8,000 steps @ 1024 px | **25,000 steps @ 1280 px** (SSIM 0.25, SH deg 2) |
| **Post-Processing** | None (tilted, hazy floaters) | **Floater/fog pruned** (1.2M → **383,351 crisp splats**, 58.3 MB) + **RANSAC gravity-aligned** (positions & quaternions) |

#### Before (v1) vs After (v2) Comparison
![Before vs After 3DGS Comparison](renders/splat_before_after.jpg)

#### v2 3D Gaussian Splat Gallery (Rendered from `apartment_splat.ply`)
![v2 3DGS Showcase Gallery](renders/splat_v2_showcase.jpg)

| Kitchen, Music Nook & Dining Lookback (3DGS v2) |
| :---: |
| ![3DGS v2 Lookback](scan/splat_v2/eval_25000/dense_0211_v2_0145.png) |

> **Tip for 100% Wall-to-Wall Perfection:** Because the original handheld videos were shot vertically (9:16) with fast doorway pans, edge areas with single-angle coverage (such as right next to the kitchen island) still have minor streaks. Shooting a slow **0.5× ultrawide landscape** loop pausing 1 second at every doorway and re-running `scripts/build_crisp_3dgs_dataset.py` + `brush_app.exe` + `scripts/postprocess_splat.py` will eliminate those remaining edge streaks too.

---

## Playable First-Person Escape Room (`web/`)

A complete browser-based **Three.js** walkthrough and 4-stage interactive escape room runs directly off `exports/apartment_escape_room.glb`:

### Quick Start
1. Double-click **`launch_walkthrough.bat`** (or run `python -m http.server 8765` from the repo root).
2. Open **`http://localhost:8765/web/`** for the First-Person Escape Room, or **`http://localhost:8765/web/splat.html`** for the 3D Gaussian Splat Viewer.

### Controls
| Key / Input | Action |
| :--- | :--- |
| `W A S D` / Arrow Keys | Walk (`Shift` to sprint) |
| `Mouse` | First-person look (Pointer Lock) |
| `E` | Interact with clues, zoom binoculars, play MIDI synth, operate 3D printer, open/close hinged doors, or use the Yale Smart Keypad |
| `F` | Toggle White LED Flashlight |
| `U` | Toggle Purple **UV Blacklight** (once printed in the Studio Office!) |
| `P` | Toggle your real colorized **COLMAP 3D Video Scan Overlay** inside the apartment |
| `1` – `4` | Instant Room Teleports (Living Room, Kitchen/Music Nook, Studio Office, Front Entryway) |
| `Esc` | Pause / close modal |

### Escape Room Puzzle Chain (Spoiler-Free Overview)
1. **Corner Living Room — Bistro Laptop & Windowsill Binoculars:** Inspect the glowing laptop overlooking the skyline, then peer through the windowsill binoculars (`E`) with a 4.5× optical zoom reticle to read the downtown rooftop beacon (**Digit #1**).
2. **Music Production Nook — Playable MIDI Synthesizer:** Open the interactive 8-key Web Audio synthesizer modal and play the ascending **C-Major-7** arpeggio (`C → E → G → B`) to decode the mixer LCD (**Digit #2**).
3. **Studio / 3D-Printer Office — Animated 3D Printer & UV Lens:** Open the Studio door and run the 3D printer (`E`) to animate the print head, collect the freshly printed **UV Blacklight Lens** into your inventory, and read the heated-bed calibration tag (**Digit #3**).
4. **East Hallway — UV Blacklight Whiteboard:** Activate UV Blacklight (`U`) and inspect your real hallway whiteboard to reveal hidden glowing neon ink (**Digit #4**).
5. **Front Entry Door — Yale Smart Keypad:** Enter the 4-digit PIN on the interactive keypad to unlock and swing open the oak front door!
6. **Bonus Easter Eggs:** Brew espresso at the kitchen coffee maker for a 15-second sprint boost, or check the microwave LCD for the digit order hint.

---

## Blender 5.3 Collections & Game Engine Import

Open **`blender/apartment_escape_room.blend`** in Blender 5.3+. Every room and puzzle prop is modular and separated into 10 Outliner collections:

| Collection | Contents |
| :--- | :--- |
| `01_Architecture` | Oak plank floors, carpeted studio, tiled bath, walls, baseboards, recessed ceiling downlights, NW corner column |
| `02_Windows_Skyline` | Wrap-around aluminum mullions, translucent glass panes, stitched panoramic city skyline backdrops |
| `03_Kitchen` | Maple cabinets with chrome pulls, granite countertops, stainless fridge, range/burners, microwave, sink/faucet, pendants, cognac bar stools |
| `04_LivingRoom` | Modular cream sectional + pillows/blanket, real jute rug, coffee table + backpack, sneakers, TV console, acoustic guitar, bistro laptop, binoculars, gaming chairs, NE desk |
| `05_MusicNook_Dining` | Dining table & chairs, real framed tattoo-hands painting, 61-key MIDI keyboard, DJ controller, mixer, studio monitors, mic stand, real handwritten whiteboard |
| `06_StudioOffice` | Foil window reflectors, dual stacked monitors, two detailed 3D printers (X-rail, extruder, cyan spool, UV lens print), cube shelf + TV, electric guitar, second desk, walk-in closet |
| `07_EntryHall_Bath` | Hinged doors with casings (`Door_FrontEntry` w/ Yale keypad, `Door_StudioOffice`, `Door_Bathroom`, `Door_LivingMaster`, `Door_Pantry`), tufted bench + vinyls, guitar case, rolling cart, graduation robe/cap + pennant, bathroom vanity/mirror/toilet/tub |
| `08_EscapeRoom_Interactables` | Named `INTERACT_*` Empty pivots with custom `escape_label` properties for Unity / Unreal / Godot trigger scripts |
| `09_3DScan_Reference` | Floor-aligned 10,283-point `COLMAP_3DScan_LivingKitchen` reference cloud (hidden by default — toggle visibility in Outliner) |
| `10_Lighting_Cameras` | Golden afternoon sun, per-room area lights, and 5 verification cameras |

### Importing into Unity / Unreal / Godot
- **Godot 4 / Three.js / WebGL:** Drag & drop `exports/apartment_escape_room.glb` directly — all 5 real photo textures, PBR materials, hinged door origins, and `INTERACT_*` markers are embedded.
- **Unity / Unreal Engine 5:** Import `exports/apartment_escape_room.fbx` (or `.glb` via glTFast / Interchange); hinged doors already have their pivot origins set on the hinge axis so rotating around local `Y` (or `Z` in Unreal) swings them smoothly.

---

## Repository Structure

```text
vaughn-apt/
├── README.md
├── launch_walkthrough.bat          # One-click local web server + browser launch
├── launch_brush_splat.bat          # Native RTX GPU viewer for apartment_splat.ply
├── blender/
│   └── apartment_escape_room.blend # Editable Blender 5.3 scene (packed textures)
├── exports/
│   ├── apartment_escape_room.glb   # glTF 2.0 (386 meshes, 45 materials, 5 images)
│   └── apartment_escape_room.fbx   # FBX with embedded textures
├── renders/                        # 5 Blender 5.3 EEVEE preview renders
├── scan/
│   ├── floorplan_analysis.png      # Gravity-aligned SfM top-down & elevation plots
│   ├── rooms_floorplan_comparison.png
│   ├── living_scan_aligned.ply     # 10,283-point floor-aligned COLMAP point cloud
│   ├── living_scan_threejs.json    # WebGL point-cloud overlay dataset
│   └── splat/
│       ├── apartment_splat.ply     # Trained Brush 3D Gaussian Splat
│       └── eval_8000/              # Rendered splat evaluation frames
├── scripts/
│   ├── extract_frames.py           # FFmpeg + OpenCV Laplacian blur filter
│   ├── run_sfm.py                  # pycolmap 4.2.1 full-apartment multi-zone SfM
│   ├── align_scan_to_level.py      # RANSAC floor-plane alignment & metric scaling
│   ├── build_crisp_3dgs_dataset.py # Dense 4096-SIFT SfM + zero-distortion PINHOLE undistorter
│   ├── postprocess_splat.py        # Binary PLY floater pruning & quaternion gravity alignment
│   └── build_apartment_blender.py  # Reproducible Blender 5.3 level generator
├── textures/                       # Real cropped apartment & skyline textures
└── web/
    ├── index.html                  # First-Person Apartment Escape Room
    ├── app.js                      # Three.js controls, collisions, puzzles, Web Audio
    ├── styles.css
    └── splat.html                  # Browser 3D Gaussian Splat Viewer
```

---

## Reproducing Locally

```powershell
# 1. Create Python 3.12 virtual environment
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe pycolmap opencv-python-headless numpy pillow matplotlib

# 2. Extract sharp frames, run SfM, align point cloud, and rebuild Blender + GLB/FBX
.venv\Scripts\python.exe scripts\extract_frames.py
.venv\Scripts\python.exe scripts\run_sfm.py
.venv\Scripts\python.exe scripts\align_scan_to_level.py
& "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --background --python scripts\build_apartment_blender.py

# 3. Rebuild crisp v2 3D Gaussian Splat (requires Brush binary in tools/brush/)
.venv\Scripts\python.exe scripts\build_crisp_3dgs_dataset.py
tools\brush\brush_app.exe scan\colmap_v2_pinhole --total-steps 25000 --refine-every 150 --growth-stop-iter 15000 --growth-grad-threshold 0.00003 --max-splats 1200000 --max-resolution 1280 --sh-degree 2 --ssim-weight 0.25 --export-every 25000 --export-path scan\splat_v2 --export-name apartment_splat_raw.ply
.venv\Scripts\python.exe scripts\postprocess_splat.py

# 4. Launch web walkthrough & 3DGS viewer
python -m http.server 8765
```
