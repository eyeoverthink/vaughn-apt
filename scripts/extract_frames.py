"""Extract sharp, blur-filtered keyframes from IMG_6804.MOV and IMG_6805.MOV for 3D reconstruction & reference."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_DIR = Path(r"C:\Users\eyeov\.gemini\antigravity\scratch\apartment-world")
VIDEOS = [
    ("v1", Path(r"C:\Users\eyeov\Downloads\IMG_6804.MOV")),
    ("v2", Path(r"C:\Users\eyeov\Downloads\IMG_6805.MOV")),
]

RAW_DIR = PROJECT_DIR / "frames" / "raw"
SHARP_DIR = PROJECT_DIR / "frames" / "sharp"
REF_DIR = PROJECT_DIR / "frames" / "reference"


def sharpness_score(img_path: Path) -> float:
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    # Compute Laplacian variance on central 80% to ignore edge vignette
    h, w = img.shape
    crop = img[int(h * 0.1) : int(h * 0.9), int(w * 0.1) : int(w * 0.9)]
    return float(cv2.Laplacian(crop, cv2.CV_64F).var())


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if SHARP_DIR.exists():
        shutil.rmtree(SHARP_DIR)
    SHARP_DIR.mkdir(parents=True, exist_ok=True)
    REF_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Load already-extracted raw candidate frames from frames/raw
    candidates: list[tuple[str, int, Path]] = []
    for prefix, _video_path in VIDEOS:
        existing = sorted(RAW_DIR.glob(f"{prefix}_*.jpg"))
        if not existing:
            print(f"ERROR: Missing raw frames for {prefix} in {RAW_DIR}", file=sys.stderr)
            sys.exit(1)
        for idx, p in enumerate(existing):
            candidates.append((prefix, idx, p))

    print(f"Total raw candidate frames: {len(candidates)}")

    # Step 2: Score sharpness and select sharpest frame per 2-frame window (effective ~2 fps, ~240 frames)
    # Also drop frames below 30% of median sharpness (heavy motion blur)
    scored = []
    for prefix, idx, p in candidates:
        score = sharpness_score(p)
        scored.append((prefix, idx, p, score))

    scores_only = [s[3] for s in scored]
    med = float(np.median(scores_only))
    min_thresh = med * 0.28
    print(f"Sharpness median={med:.1f}, min={min(scores_only):.1f}, max={max(scores_only):.1f}, thresh={min_thresh:.1f}")

    selected = []
    by_prefix: dict[str, list[tuple[str, int, Path, float]]] = {}
    for item in scored:
        by_prefix.setdefault(item[0], []).append(item)

    frame_counter = 1
    metadata = []
    window = 2  # pick best of every 2 frames (= 0.5s window at 4fps -> ~2 fps)
    for prefix, items in by_prefix.items():
        for i in range(0, len(items), window):
            chunk = items[i : i + window]
            best = max(chunk, key=lambda x: x[3])
            if best[3] < min_thresh:
                continue
            dst_name = f"frame_{frame_counter:04d}_{prefix}_{best[1]:04d}.jpg"
            dst = SHARP_DIR / dst_name
            shutil.copy2(best[2], dst)
            selected.append(dst)
            metadata.append(
                {
                    "file": dst_name,
                    "video": prefix,
                    "time_sec": round(best[1] / 4.0, 2),
                    "sharpness": round(best[3], 1),
                }
            )
            frame_counter += 1

    (PROJECT_DIR / "frames" / "frames_meta.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"Selected {len(selected)} sharp frames into {SHARP_DIR}")


if __name__ == "__main__":
    main()
