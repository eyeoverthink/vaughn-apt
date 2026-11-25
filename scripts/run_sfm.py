"""Run pycolmap Structure-from-Motion reconstruction and generate gravity-aligned floorplan analysis."""
import json
import shutil
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pycolmap

PROJECT_DIR = Path(r"C:\Users\eyeov\.gemini\antigravity\scratch\apartment-world")
IMAGE_DIR = PROJECT_DIR / "frames" / "sharp"
SCAN_DIR = PROJECT_DIR / "scan"
DB_PATH = SCAN_DIR / "database.db"
SPARSE_DIR = SCAN_DIR / "sparse"


def align_to_gravity_and_scale(rec: pycolmap.Reconstruction):
    """Align reconstruction so +Z is world up (from camera up vectors) and scale roughly to meters."""
    cam_centers = []
    cam_ups = []
    for img in rec.images.values():
        if not img.has_pose:
            continue
        pose = img.cam_from_world() if callable(img.cam_from_world) else img.cam_from_world
        R = pose.rotation.matrix()  # world-to-cam
        t = pose.translation
        center = -R.T @ t
        # In COLMAP camera coords: +X right, +Y down, +Z forward -> camera up in world is -R.T @ [0,1,0]
        up_world = -R.T @ np.array([0.0, 1.0, 0.0])
        cam_centers.append(center)
        cam_ups.append(up_world)

    cam_centers = np.array(cam_centers)
    cam_ups = np.array(cam_ups)

    # Mean up vector -> align to +Z
    mean_up = np.mean(cam_ups, axis=0)
    mean_up /= np.linalg.norm(mean_up) + 1e-9

    z_axis = np.array([0.0, 0.0, 1.0])
    v = np.cross(mean_up, z_axis)
    s = np.linalg.norm(v)
    c = float(np.dot(mean_up, z_axis))
    if s < 1e-6:
        R_up = np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R_up = np.eye(3) + vx + (vx @ vx) * ((1.0 - c) / (s * s))

    # Extract 3D points
    pts = []
    cols = []
    for pt in rec.points3D.values():
        if pt.track.length() >= 3 and pt.error < 2.5:
            pts.append(pt.xyz)
            cols.append(pt.color)
    pts = np.array(pts)
    cols = np.array(cols, dtype=np.uint8)

    pts_rot = (R_up @ pts.T).T
    cams_rot = (R_up @ cam_centers.T).T

    # Rotate around Z so dominant wall direction aligns with X/Y axes (via 2D PCA of camera path or wall gradients)
    # Use robust percentile bounding box & principal directions of interior points
    z_med_cam = float(np.median(cams_rot[:, 2]))
    # Estimate floor Z as 5th percentile of points below camera
    below_cam = pts_rot[pts_rot[:, 2] < z_med_cam]
    floor_z = float(np.percentile(below_cam[:, 2], 5)) if len(below_cam) > 50 else float(np.percentile(pts_rot[:, 2], 5))
    cam_height_raw = z_med_cam - floor_z

    # Assume handheld walkthrough camera is ~1.35m above floor
    scale = 1.35 / max(cam_height_raw, 1e-3)
    pts_scaled = (pts_rot - np.array([0.0, 0.0, floor_z])) * scale
    cams_scaled = (cams_rot - np.array([0.0, 0.0, floor_z])) * scale

    # Center XY at median of cameras
    xy_origin = np.median(cams_scaled[:, :2], axis=0)
    pts_scaled[:, :2] -= xy_origin
    cams_scaled[:, :2] -= xy_origin

    # Align dominant horizontal axis via histogram of wall segment orientations or PCA of wall points (0.4m < z < 2.3m)
    wall_mask = (pts_scaled[:, 2] > 0.4) & (pts_scaled[:, 2] < 2.3)
    wall_xy = pts_scaled[wall_mask, :2]
    # Trim extreme outliers (outdoor city buildings seen through windows!)
    r = np.linalg.norm(wall_xy, axis=1)
    interior_xy = wall_xy[r < 12.0]
    if len(interior_xy) > 50:
        cov = np.cov(interior_xy.T)
        eigvals, eigvecs = np.linalg.eigh(cov)
        main_axis = eigvecs[:, 1]  # largest variance
        angle = np.arctan2(main_axis[1], main_axis[0])
        ca, sa = np.cos(-angle), np.sin(-angle)
        Rz = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])
        pts_scaled = (Rz @ pts_scaled.T).T
        cams_scaled = (Rz @ cams_scaled.T).T
    else:
        Rz = np.eye(3)

    return pts_scaled, cols, cams_scaled, scale, Rz @ R_up


def write_ply(path: Path, pts: np.ndarray, cols: np.ndarray) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(pts)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("end_header\n")
        for (x, y, z), (r, g, b) in zip(pts, cols):
            f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(r)} {int(g)} {int(b)}\n")


def main() -> None:
    t0 = time.time()
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    if SPARSE_DIR.exists():
        shutil.rmtree(SPARSE_DIR)
    SPARSE_DIR.mkdir(parents=True, exist_ok=True)

    images = sorted(IMAGE_DIR.glob("*.jpg"))
    print(f"Found {len(images)} sharp frames in {IMAGE_DIR}")

    print("[1/3] Extracting SIFT features...")
    reader_opts = pycolmap.ImageReaderOptions()
    reader_opts.camera_model = "SIMPLE_RADIAL"
    extraction_opts = pycolmap.FeatureExtractionOptions()
    extraction_opts.max_image_size = 1280
    if hasattr(extraction_opts, "sift"):
        extraction_opts.sift.max_num_features = 2500
    pycolmap.extract_features(
        database_path=str(DB_PATH),
        image_path=str(IMAGE_DIR),
        camera_mode=pycolmap.CameraMode.SINGLE,
        reader_options=reader_opts,
        extraction_options=extraction_opts,
    )
    print(f"  Feature extraction done in {time.time() - t0:.1f}s")

    print("[2/3] Running exhaustive matching...")
    t1 = time.time()
    pycolmap.match_exhaustive(database_path=str(DB_PATH))
    print(f"  Matching done in {time.time() - t1:.1f}s")

    print("[3/3] Running incremental mapping...")
    t2 = time.time()
    maps = pycolmap.incremental_mapping(
        database_path=str(DB_PATH),
        image_path=str(IMAGE_DIR),
        output_path=str(SPARSE_DIR),
    )
    print(f"  Incremental mapping done in {time.time() - t2:.1f}s; models={len(maps)}")

    if not maps:
        print("ERROR: No reconstruction produced!")
        return

    # Inspect all reconstructed sub-models
    summary = []
    best_idx = max(maps.keys(), key=lambda k: maps[k].num_reg_images())
    for idx, rec in maps.items():
        reg_names = sorted(img.name for img in rec.images.values() if img.has_pose)
        info = {
            "model_id": int(idx),
            "num_reg_images": int(rec.num_reg_images()),
            "num_points3D": int(rec.num_points3D()),
            "first_image": reg_names[0] if reg_names else "",
            "last_image": reg_names[-1] if reg_names else "",
            "v1_count": sum(1 for n in reg_names if "_v1_" in n),
            "v2_count": sum(1 for n in reg_names if "_v2_" in n),
        }
        summary.append(info)
        print(f"Model {idx}: {info}")
        out_dir = SPARSE_DIR / str(idx)
        out_dir.mkdir(parents=True, exist_ok=True)
        rec.write(str(out_dir))

    # Align and export the best model (and any secondary model with >=15 images)
    best_rec = maps[best_idx]
    pts, cols, cams, scale, rot = align_to_gravity_and_scale(best_rec)
    write_ply(SCAN_DIR / "points3D_aligned.ply", pts, cols)

    # Filter interior points (within 10m of cameras, height -0.3m to 3.5m) for clean floorplan plot
    cam_min = cams.min(axis=0) - np.array([2.5, 2.5, 0.5])
    cam_max = cams.max(axis=0) + np.array([2.5, 2.5, 2.2])
    in_box = (
        (pts[:, 0] >= cam_min[0]) & (pts[:, 0] <= cam_max[0]) &
        (pts[:, 1] >= cam_min[1]) & (pts[:, 1] <= cam_max[1]) &
        (pts[:, 2] >= -0.3) & (pts[:, 2] <= 3.5)
    )
    pts_in = pts[in_box]
    cols_in = cols[in_box]
    write_ply(SCAN_DIR / "points3D_interior.ply", pts_in, cols_in)

    # Generate Top-Down Floorplan + Side Elevation plots with 1m grid!
    fig, axes = plt.subplots(1, 2, figsize=(16, 8), dpi=150)

    ax = axes[0]
    wall_sel = (pts_in[:, 2] > 0.35) & (pts_in[:, 2] < 2.6)
    ax.scatter(pts_in[wall_sel, 0], pts_in[wall_sel, 1], c=cols_in[wall_sel] / 255.0, s=1.5, alpha=0.65)
    ax.plot(cams[:, 0], cams[:, 1], "r-", linewidth=1.2, alpha=0.8, label="Camera path")
    # Mark every 10th camera with its index
    for i in range(0, len(cams), max(1, len(cams) // 15)):
        ax.scatter(cams[i, 0], cams[i, 1], c="red", s=18, zorder=5)
        ax.text(cams[i, 0] + 0.1, cams[i, 1] + 0.1, str(i), fontsize=7, color="darkred")
    ax.set_aspect("equal")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)
    ax.set_xlabel("X (meters)")
    ax.set_ylabel("Y (meters)")
    ax.set_title(f"Top-Down Floorplan (Model {best_idx}: {best_rec.num_reg_images()} imgs, {len(pts_in)} interior pts)")
    ax.legend()

    ax2 = axes[1]
    ax2.scatter(pts_in[:, 0], pts_in[:, 2], c=cols_in / 255.0, s=1.2, alpha=0.5)
    ax2.plot(cams[:, 0], cams[:, 2], "r-", linewidth=1.2, label="Camera Z")
    ax2.set_aspect("equal")
    ax2.grid(True, linestyle="--", alpha=0.4)
    ax2.set_xlabel("X (meters)")
    ax2.set_ylabel("Z height (meters)")
    ax2.set_title("Side Elevation (X-Z)")
    ax2.legend()

    plt.tight_layout()
    plt.savefig(SCAN_DIR / "floorplan_analysis.png")
    plt.close(fig)

    # Save camera poses & layout stats
    reg_imgs = sorted(
        [img for img in best_rec.images.values() if img.has_pose],
        key=lambda im: im.name,
    )
    cam_records = []
    for im, pos in zip(reg_imgs, cams):
        cam_records.append({
            "name": im.name,
            "pos": [round(float(v), 3) for v in pos],
        })

    stats = {
        "best_model": int(best_idx),
        "all_models": summary,
        "estimated_scale_to_meters": round(float(scale), 4),
        "interior_bbox_min_m": [round(float(v), 2) for v in pts_in.min(axis=0)] if len(pts_in) else [],
        "interior_bbox_max_m": [round(float(v), 2) for v in pts_in.max(axis=0)] if len(pts_in) else [],
        "camera_bbox_min_m": [round(float(v), 2) for v in cams.min(axis=0)],
        "camera_bbox_max_m": [round(float(v), 2) for v in cams.max(axis=0)],
        "cameras": cam_records,
    }
    (SCAN_DIR / "layout_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Saved floorplan analysis and {len(pts_in)} interior points to {SCAN_DIR}")
    print(f"Total elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
