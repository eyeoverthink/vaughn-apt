"""Build a dense, ultra-sharp, undistorted PINHOLE COLMAP dataset for crisp 3D Gaussian Splatting."""
import json
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
import pycolmap

PROJECT_DIR = Path(r"C:\Users\eyeov\.gemini\antigravity\scratch\apartment-world")
RAW_DIR = PROJECT_DIR / "frames" / "raw"
WORK_DIR = PROJECT_DIR / "scan" / "colmap_v2_work"
IMG_SRC_DIR = WORK_DIR / "images"
DB_PATH = WORK_DIR / "database.db"
SPARSE_DIR = WORK_DIR / "sparse"
PINHOLE_DIR = PROJECT_DIR / "scan" / "colmap_v2_pinhole"
SPLAT_V2_DIR = PROJECT_DIR / "scan" / "splat_v2"


def sharpness(img_path: Path) -> float:
    im = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if im is None:
        return 0.0
    h, w = im.shape
    crop = im[int(h * 0.1) : int(h * 0.9), int(w * 0.1) : int(w * 0.9)]
    return float(cv2.Laplacian(crop, cv2.CV_64F).var())


def ransac_floor_rotation(rec: pycolmap.Reconstruction):
    """Compute gravity-up rotation aligning the living-room floor plane to +Y-down (COLMAP) -> Y-up (Three.js)."""
    pts, cam_centers, cam_ups = [], [], []
    for pt in rec.points3D.values():
        if pt.track.length() >= 3 and pt.error < 2.0:
            pts.append(pt.xyz)
    for img in rec.images.values():
        if not img.has_pose:
            continue
        pose = img.cam_from_world() if callable(img.cam_from_world) else img.cam_from_world
        R = pose.rotation.matrix()
        t = pose.translation
        cam_centers.append(-R.T @ t)
        cam_ups.append(-R.T @ np.array([0.0, 1.0, 0.0]))
    pts = np.array(pts)
    cam_centers = np.array(cam_centers)
    mean_up = np.mean(cam_ups, axis=0)
    mean_up /= np.linalg.norm(mean_up) + 1e-9

    cam_med = np.median(cam_centers, axis=0)
    dists = np.linalg.norm(pts - cam_med, axis=1)
    r85 = float(np.percentile(dists, 82))
    pts_in = pts[dists < r85]

    proj = (pts_in - cam_med) @ mean_up
    floor_cands = pts_in[proj < np.percentile(proj, 45)]

    rng = np.random.default_rng(42)
    best_inliers, best_cnt = None, 0
    thresh = 0.035 * r85
    for _ in range(1200):
        p0, p1, p2 = floor_cands[rng.choice(len(floor_cands), 3, replace=False)]
        n = np.cross(p1 - p0, p2 - p0)
        ln = np.linalg.norm(n)
        if ln < 1e-6:
            continue
        n /= ln
        inliers = np.abs((floor_cands - p0) @ n) < thresh
        cnt = int(inliers.sum())
        if cnt > best_cnt:
            best_cnt, best_inliers = cnt, inliers

    inlier_pts = floor_cands[best_inliers]
    centroid = inlier_pts.mean(axis=0)
    _, _, vt = np.linalg.svd(inlier_pts - centroid, full_matrices=False)
    normal = vt[-1]
    normal /= np.linalg.norm(normal)
    if np.dot(normal, mean_up) < 0:
        normal = -normal

    # Align floor normal to +Y (so Three.js Y-up viewer shows the room dead level and upright!)
    target = np.array([0.0, 1.0, 0.0])
    v = np.cross(normal, target)
    s = np.linalg.norm(v)
    c = float(np.dot(normal, target))
    if s < 1e-6:
        R_up = np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R_up = np.eye(3) + vx + (vx @ vx) * ((1.0 - c) / (s * s))

    cam_rot = (R_up @ (cam_centers - centroid).T).T
    cam_origin = np.median(cam_rot, axis=0)
    return R_up, centroid, cam_origin, int(best_cnt)


def main() -> None:
    t0 = time.time()
    for d in (WORK_DIR, PINHOLE_DIR):
        if d.exists():
            shutil.rmtree(d)
    IMG_SRC_DIR.mkdir(parents=True, exist_ok=True)
    SPARSE_DIR.mkdir(parents=True, exist_ok=True)
    PINHOLE_DIR.mkdir(parents=True, exist_ok=True)
    SPLAT_V2_DIR.mkdir(parents=True, exist_ok=True)

    # Select dense, high-overlap, ultra-sharp frames across Living Room + Dining + Kitchen:
    # - v1_0235..v1_0340 (kitchen -> dining -> music nook -> living room entry)
    # - v2_0001..v2_0156 (full corner living room, windows, sectional, desks, lookback)
    cands = []
    for i in range(235, 345):
        p = RAW_DIR / f"v1_{i:04d}.jpg"
        if p.exists():
            cands.append(("v1", i, p))
    for i in range(1, 160):
        p = RAW_DIR / f"v2_{i:04d}.jpg"
        if p.exists():
            cands.append(("v2", i, p))

    scored = [(pre, idx, p, sharpness(p)) for pre, idx, p in cands]
    med = float(np.median([s[3] for s in scored]))
    # Strict sharpness gate to banish motion blur!
    min_sharp = max(95.0, med * 0.42)
    kept = [s for s in scored if s[3] >= min_sharp]
    print(f"Dense Living/Kitchen candidates: {len(scored)}, median sharpness={med:.1f}, thresh={min_sharp:.1f}, kept={len(kept)}")

    for k, (pre, idx, p, sc) in enumerate(kept, 1):
        dst = IMG_SRC_DIR / f"dense_{k:04d}_{pre}_{idx:04d}.jpg"
        shutil.copy2(p, dst)

    # Step 1: High-detail SIFT feature extraction (SINGLE_CAMERA, SIMPLE_RADIAL)
    print("[1/4] Extracting high-detail SIFT features (4096/img)...")
    reader_opts = pycolmap.ImageReaderOptions()
    reader_opts.camera_model = "SIMPLE_RADIAL"
    ext_opts = pycolmap.FeatureExtractionOptions()
    ext_opts.max_image_size = 1280
    if hasattr(ext_opts, "sift"):
        ext_opts.sift.max_num_features = 4096
    pycolmap.extract_features(
        database_path=str(DB_PATH),
        image_path=str(IMG_SRC_DIR),
        camera_mode=pycolmap.CameraMode.SINGLE,
        reader_options=reader_opts,
        extraction_options=ext_opts,
    )

    # Step 2: Exhaustive matching for rock-solid multi-pass loop closure
    print("[2/4] Running exhaustive feature matching...")
    pycolmap.match_exhaustive(database_path=str(DB_PATH))

    # Step 3: Incremental SfM mapping
    print("[3/4] Running incremental SfM mapping...")
    maps = pycolmap.incremental_mapping(
        database_path=str(DB_PATH),
        image_path=str(IMG_SRC_DIR),
        output_path=str(SPARSE_DIR),
    )
    if not maps:
        raise RuntimeError("SfM failed to produce any model!")

    best_idx = max(maps.keys(), key=lambda k: maps[k].num_reg_images())
    best_rec = maps[best_idx]
    best_dir = SPARSE_DIR / str(best_idx)
    best_dir.mkdir(parents=True, exist_ok=True)
    best_rec.write(str(best_dir))
    print(f"Best model #{best_idx}: {best_rec.num_reg_images()} / {len(kept)} images registered, {best_rec.num_points3D()} 3D points")

    # Step 4: Undistort to exact zero-distortion PINHOLE dataset for Brush 3DGS!
    print("[4/4] Undistorting images to exact PINHOLE model for Brush 3DGS...")
    undist_opts = pycolmap.UndistortCameraOptions()
    undist_opts.max_image_size = 1280
    pycolmap.undistort_images(
        output_path=str(PINHOLE_DIR),
        input_path=str(best_dir),
        image_path=str(IMG_SRC_DIR),
        output_type="COLMAP",
        undistort_options=undist_opts,
    )

    # Brush expects sparse/0/ under dataset root; undistort_images writes directly into sparse/
    sp_root = PINHOLE_DIR / "sparse"
    sp_zero = sp_root / "0"
    if not sp_zero.exists():
        sp_zero.mkdir(parents=True, exist_ok=True)
        for fname in ("cameras.bin", "images.bin", "points3D.bin"):
            f = sp_root / fname
            if f.exists():
                shutil.move(str(f), str(sp_zero / fname))

    # Compute & save gravity alignment from the undistorted model!
    pin_rec = pycolmap.Reconstruction(str(sp_zero))
    R_up, centroid, cam_origin, inliers = ransac_floor_rotation(pin_rec)
    meta = {
        "reg_images": int(pin_rec.num_reg_images()),
        "points3D": int(pin_rec.num_points3D()),
        "floor_inliers": inliers,
        "R_up": R_up.tolist(),
        "centroid": centroid.tolist(),
        "cam_origin": cam_origin.tolist(),
    }
    (SPLAT_V2_DIR / "align_transform.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Pinhole 3DGS dataset ready in {PINHOLE_DIR} ({pin_rec.num_reg_images()} imgs, {pin_rec.num_points3D()} pts) in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
