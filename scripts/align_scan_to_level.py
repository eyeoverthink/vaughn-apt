"""Fit a flat horizontal floor plane to COLMAP Model 0 and align it to the apartment Living Room coordinates."""
import json
from pathlib import Path

import numpy as np
import pycolmap

PROJECT_DIR = Path(r"C:\Users\eyeov\.gemini\antigravity\scratch\apartment-world")
SCAN_DIR = PROJECT_DIR / "scan"


def ransac_plane(pts: np.ndarray, iters: int = 800, thresh: float = 0.08):
    rng = np.random.default_rng(42)
    best_inliers = None
    best_count = 0
    best_normal = np.array([0.0, 0.0, 1.0])
    n = len(pts)
    for _ in range(iters):
        idx = rng.choice(n, 3, replace=False)
        p0, p1, p2 = pts[idx]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = np.linalg.norm(normal)
        if norm < 1e-6:
            continue
        normal /= norm
        d = -np.dot(normal, p0)
        dist = np.abs(pts @ normal + d)
        inliers = dist < thresh
        cnt = int(inliers.sum())
        if cnt > best_count:
            best_count = cnt
            best_inliers = inliers
            best_normal = normal
    # Refine via SVD on inliers
    inlier_pts = pts[best_inliers]
    centroid = inlier_pts.mean(axis=0)
    _, _, vt = np.linalg.svd(inlier_pts - centroid, full_matrices=False)
    normal = vt[-1]
    normal /= np.linalg.norm(normal)
    return normal, centroid, best_count


def rot_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a / (np.linalg.norm(a) + 1e-9)
    b = b / (np.linalg.norm(b) + 1e-9)
    v = np.cross(a, b)
    s = np.linalg.norm(v)
    c = float(np.dot(a, b))
    if s < 1e-6:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + (vx @ vx) * ((1.0 - c) / (s * s))


def write_ply(path: Path, pts: np.ndarray, cols: np.ndarray) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(pts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        f.write("end_header\n")
        for (x, y, z), (r, g, b) in zip(pts, cols):
            f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(r)} {int(g)} {int(b)}\n")


def main() -> None:
    rec = pycolmap.Reconstruction(str(SCAN_DIR / "sparse" / "0"))
    pts, cols = [], []
    for pt in rec.points3D.values():
        if pt.track.length() >= 3 and pt.error < 2.2:
            pts.append(pt.xyz)
            cols.append(pt.color)
    pts = np.array(pts)
    cols = np.array(cols, dtype=np.uint8)

    cam_centers, cam_ups = [], []
    for img in rec.images.values():
        if not img.has_pose:
            continue
        pose = img.cam_from_world() if callable(img.cam_from_world) else img.cam_from_world
        R = pose.rotation.matrix()
        t = pose.translation
        cam_centers.append(-R.T @ t)
        cam_ups.append(-R.T @ np.array([0.0, 1.0, 0.0]))
    cam_centers = np.array(cam_centers)
    mean_up = np.mean(cam_ups, axis=0)
    mean_up /= np.linalg.norm(mean_up) + 1e-9

    # Keep interior cloud near cameras (remove distant skyline outliers)
    cam_med = np.median(cam_centers, axis=0)
    dists = np.linalg.norm(pts - cam_med, axis=1)
    r90 = float(np.percentile(dists, 82))
    interior = dists < r90
    pts_in = pts[interior]
    cols_in = cols[interior]

    # Fit dominant plane (the woven rug + living room floor!) via RANSAC
    # Select lower half along rough up axis to bias toward floor
    proj_up = (pts_in - cam_med) @ mean_up
    floor_candidates = pts_in[proj_up < np.percentile(proj_up, 45)]
    normal, floor_centroid, cnt = ransac_plane(floor_candidates, iters=1200, thresh=0.04 * r90)
    if np.dot(normal, mean_up) < 0:
        normal = -normal

    R_flat = rot_between(normal, np.array([0.0, 0.0, 1.0]))
    pts_flat = (R_flat @ (pts_in - floor_centroid).T).T
    cams_flat = (R_flat @ (cam_centers - floor_centroid).T).T

    # Ensure cameras are ABOVE the floor plane (+Z)
    if float(np.median(cams_flat[:, 2])) < 0:
        pts_flat[:, 2] *= -1.0
        cams_flat[:, 2] *= -1.0

    # Floor Z should be at ~0 (use 5th percentile of interior points below cameras)
    cam_z_raw = float(np.median(cams_flat[:, 2]))
    below = pts_flat[pts_flat[:, 2] < cam_z_raw]
    z_floor = float(np.percentile(below[:, 2], 5)) if len(below) > 50 else float(np.percentile(pts_flat[:, 2], 5))
    pts_flat[:, 2] -= z_floor
    cams_flat[:, 2] -= z_floor

    # Scale so median camera height above floor is 1.45 m
    cam_z_med = abs(float(np.median(cams_flat[:, 2])))
    scale = 1.45 / max(cam_z_med, 1e-2)
    pts_m = pts_flat * scale
    cams_m = cams_flat * scale

    # Align main living room axis with Y (+Y north)
    xy = pts_m[(pts_m[:, 2] >= -0.2) & (pts_m[:, 2] < 3.0), :2]
    if len(xy) < 20:
        xy = pts_m[:, :2]
    cov = np.cov(xy.T)
    _, eigvecs = np.linalg.eigh(cov)
    long_axis = eigvecs[:, 1]
    # Rotate so long_axis aligns with +Y
    ang = np.arctan2(long_axis[1], long_axis[0]) - np.pi / 2.0
    ca, sa = np.cos(-ang), np.sin(-ang)
    Rz = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])
    pts_m = (Rz @ pts_m.T).T
    cams_m = (Rz @ cams_m.T).T

    # Center cloud into Living Room area (X ~ -1.1, Y ~ 4.3)
    p_med = np.median(pts_m[:, :2], axis=0)
    pts_m[:, 0] = pts_m[:, 0] - p_med[0] - 1.1
    pts_m[:, 1] = pts_m[:, 1] - p_med[1] + 4.3
    # Keep sensible interior Z
    keep = (pts_m[:, 2] > -0.15) & (pts_m[:, 2] < 2.95) & (pts_m[:, 0] > -4.2) & (pts_m[:, 0] < 2.2) & (pts_m[:, 1] > -2.5) & (pts_m[:, 1] < 7.8)
    pts_m = pts_m[keep]
    cols_m = cols_in[keep]

    write_ply(SCAN_DIR / "living_scan_aligned.ply", pts_m, cols_m)

    # Also save compact JSON for Three.js point cloud toggle (max 6000 pts)
    step = max(1, len(pts_m) // 6000)
    sub_p = pts_m[::step]
    sub_c = cols_m[::step]
    # Convert Blender Z-up (x, y, z) -> Three.js Y-up (x, z, -y)
    three_pos = []
    three_col = []
    for (x, y, z), (r, g, b) in zip(sub_p, sub_c):
        three_pos.extend([round(float(x), 3), round(float(z), 3), round(float(-y), 3)])
        three_col.extend([round(r / 255.0, 3), round(g / 255.0, 3), round(b / 255.0, 3)])

    (SCAN_DIR / "living_scan_threejs.json").write_text(
        json.dumps({"count": len(sub_p), "positions": three_pos, "colors": three_col}),
        encoding="utf-8",
    )
    print(f"Aligned floor plane (inliers={cnt}, scale={scale:.3f}): saved {len(pts_m)} PLY pts & {len(sub_p)} Three.js pts")


if __name__ == "__main__":
    main()
