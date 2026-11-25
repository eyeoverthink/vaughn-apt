"""Post-process Brush 3DGS binary PLY: prune blurry floaters/fog, gravity-align positions & quaternions."""
import json
from pathlib import Path

import numpy as np

PROJECT_DIR = Path(r"C:\Users\eyeov\.gemini\antigravity\scratch\apartment-world")
RAW_PLY = PROJECT_DIR / "scan" / "splat_v2" / "apartment_splat_raw.ply"
ALIGN_JSON = PROJECT_DIR / "scan" / "splat_v2" / "align_transform.json"
OUT_PLY = PROJECT_DIR / "scan" / "splat" / "apartment_splat.ply"


def rot_matrix_to_quat_wxyz(R: np.ndarray) -> np.ndarray:
    """Convert 3x3 rotation matrix to unit quaternion [w, x, y, z]."""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        S = np.sqrt(tr + 1.0) * 2
        w = 0.25 * S
        x = (R[2, 1] - R[1, 2]) / S
        y = (R[0, 2] - R[2, 0]) / S
        z = (R[1, 0] - R[0, 1]) / S
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        S = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / S
        x = 0.25 * S
        y = (R[0, 1] + R[1, 0]) / S
        z = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / S
        x = (R[0, 1] + R[1, 0]) / S
        y = 0.25 * S
        z = (R[1, 2] + R[2, 1]) / S
    else:
        S = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / S
        x = (R[0, 2] + R[2, 0]) / S
        y = (R[1, 2] + R[2, 1]) / S
        z = 0.25 * S
    q = np.array([w, x, y, z], dtype=np.float64)
    return q / np.linalg.norm(q)


def quat_mul_wxyz(q: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Left-multiply quaternion q (4,) with array of quaternions p (N, 4) in [w,x,y,z]."""
    w1, x1, y1, z1 = q
    w2, x2, y2, z2 = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
    return np.stack([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ], axis=1)


def read_binary_ply(path: Path):
    with open(path, "rb") as f:
        header_lines = []
        while True:
            line = f.readline().decode("ascii")
            header_lines.append(line)
            if line.strip() == "end_header":
                break
        props = []
        n_verts = 0
        type_map = {"float": "<f4", "double": "<f8", "uchar": "u1", "int": "<i4"}
        for line in header_lines:
            parts = line.strip().split()
            if len(parts) == 3 and parts[0] == "element" and parts[1] == "vertex":
                n_verts = int(parts[2])
            elif len(parts) == 3 and parts[0] == "property":
                props.append((parts[2], type_map[parts[1]]))
        dtype = np.dtype(props)
        data = np.frombuffer(f.read(n_verts * dtype.itemsize), dtype=dtype).copy()
    return header_lines, data


def write_binary_ply(path: Path, header_lines: list[str], data: np.ndarray) -> None:
    new_header = []
    for line in header_lines:
        if line.startswith("element vertex"):
            new_header.append(f"element vertex {len(data)}\n")
        else:
            new_header.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write("".join(new_header).encode("ascii"))
        f.write(data.tobytes())


def main() -> None:
    header, data = read_binary_ply(RAW_PLY)
    n_orig = len(data)
    print(f"Loaded {RAW_PLY.name}: {n_orig:,} splats ({RAW_PLY.stat().st_size / 1e6:.1f} MB)")

    # 1) Prune transparent fog splats & giant streaky needle floaters
    opac_prob = 1.0 / (1.0 + np.exp(-np.clip(data["opacity"].astype(np.float64), -20, 20)))
    s0 = np.exp(np.clip(data["scale_0"].astype(np.float64), -12, 6))
    s1 = np.exp(np.clip(data["scale_1"].astype(np.float64), -12, 6))
    s2 = np.exp(np.clip(data["scale_2"].astype(np.float64), -12, 6))
    s_max = np.maximum(np.maximum(s0, s1), s2)
    s_min = np.minimum(np.minimum(s0, s1), s2) + 1e-8
    aspect = s_max / s_min

    scale_cap = float(np.percentile(s_max, 99.2))
    pts = np.stack([data["x"], data["y"], data["z"]], axis=1).astype(np.float64)
    med_pt = np.median(pts, axis=0)
    dist = np.linalg.norm(pts - med_pt, axis=1)
    dist_cap = float(np.percentile(dist, 99.0))

    keep = (opac_prob >= 0.05) & (s_max <= scale_cap) & (aspect < 50.0) & (dist <= dist_cap)
    data = data[keep]
    pts = pts[keep]
    print(f"Pruned floaters/fog: kept {len(data):,} / {n_orig:,} splats ({100.0 * len(data) / n_orig:.1f}%)")

    # 2) Apply exact RANSAC floor-plane gravity alignment to BOTH positions & quaternions!
    if ALIGN_JSON.exists():
        meta = json.loads(ALIGN_JSON.read_text(encoding="utf-8"))
        R_up = np.array(meta["R_up"], dtype=np.float64)
        centroid = np.array(meta["centroid"], dtype=np.float64)
        cam_origin = np.array(meta["cam_origin"], dtype=np.float64)

        pts_rot = (R_up @ (pts - centroid).T).T - cam_origin
        data["x"] = pts_rot[:, 0].astype(np.float32)
        data["y"] = pts_rot[:, 1].astype(np.float32)
        data["z"] = pts_rot[:, 2].astype(np.float32)

        q_align = rot_matrix_to_quat_wxyz(R_up)
        q_orig = np.stack([data["rot_0"], data["rot_1"], data["rot_2"], data["rot_3"]], axis=1).astype(np.float64)
        q_norm = np.linalg.norm(q_orig, axis=1, keepdims=True) + 1e-12
        q_new = quat_mul_wxyz(q_align, q_orig / q_norm)
        data["rot_0"] = q_new[:, 0].astype(np.float32)
        data["rot_1"] = q_new[:, 1].astype(np.float32)
        data["rot_2"] = q_new[:, 2].astype(np.float32)
        data["rot_3"] = q_new[:, 3].astype(np.float32)
        print("Applied exact gravity alignment to positions and Gaussian quaternions!")

    # Ensure output stays safely under GitHub's 100MB limit (< 80 MB)
    max_splats_gh = 420_000
    if len(data) > max_splats_gh:
        # Keep highest-opacity, crispest splats
        score = 1.0 / (1.0 + np.exp(-np.clip(data["opacity"], -20, 20)))
        top_idx = np.argpartition(score, -max_splats_gh)[-max_splats_gh:]
        data = data[top_idx]
        print(f"Capped to top {len(data):,} highest-opacity splats for fast WebGL + GitHub (<80 MB)")

    write_binary_ply(OUT_PLY, header, data)
    print(f"Wrote clean aligned splat: {OUT_PLY} ({OUT_PLY.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
