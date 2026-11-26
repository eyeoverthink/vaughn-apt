"""One-command Scan-Your-Own-Home pipeline runner (Phase 5 Onboarding):
Turns any smartphone walkthrough video(s) into a crisp PINHOLE 3D Gaussian Splat + Blender 5.3 Home OS world.

Usage:
  .venv\Scripts\python.exe scripts\scan_my_home.py --video path\to\walkthrough.mov [--steps 25000]
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_DIR / "frames" / "raw"
BRUSH_EXE = PROJECT_DIR / "tools" / "brush" / "brush_app.exe"


def run(cmd: list[str]) -> None:
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Turn a home walkthrough video into a Spatial Reality OS 3D world.")
    ap.add_argument("--video", nargs="+", required=True, help="One or more walkthrough video paths (.mov / .mp4)")
    ap.add_argument("--fps", type=float, default=4.0, help="Frame extraction rate (default: 4 fps)")
    ap.add_argument("--steps", type=int, default=25000, help="Brush 3DGS training steps (default: 25000)")
    ap.add_argument("--skip-brush", action="store_true", help="Skip 3DGS training if Brush binary is not installed")
    args = ap.parse_args()

    if RAW_DIR.exists():
        shutil.rmtree(RAW_DIR)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Extract frames from user video(s)
    for idx, vpath in enumerate(args.video, 1):
        vp = Path(vpath)
        if not vp.exists():
            print(f"ERROR: Video not found: {vp}", file=sys.stderr)
            sys.exit(1)
        run([
            "ffmpeg", "-y", "-i", str(vp),
            "-vf", f"fps={args.fps},scale='if(gt(iw,ih),1280,-2)':'if(gt(iw,ih),-2,1280)'",
            "-q:v", "2", str(RAW_DIR / f"v{idx}_%04d.jpg"), "-loglevel", "error",
        ])

    py = sys.executable
    # 2. Build dense undistorted PINHOLE SfM dataset
    run([py, str(PROJECT_DIR / "scripts" / "build_crisp_3dgs_dataset.py")])

    # 3. Train crisp 3D Gaussian Splat with Brush & post-process
    if not args.skip_brush and BRUSH_EXE.exists():
        run([
            str(BRUSH_EXE),
            str(PROJECT_DIR / "scan" / "colmap_v2_pinhole"),
            "--total-steps", str(args.steps),
            "--refine-every", "150",
            "--growth-stop-iter", str(min(15000, int(args.steps * 0.6))),
            "--growth-grad-threshold", "0.00003",
            "--max-splats", "1200000",
            "--max-resolution", "1280",
            "--sh-degree", "2",
            "--ssim-weight", "0.25",
            "--export-every", str(args.steps),
            "--export-path", str(PROJECT_DIR / "scan" / "splat_v2"),
            "--export-name", "apartment_splat_raw.ply",
        ])
        run([py, str(PROJECT_DIR / "scripts" / "postprocess_splat.py")])
    else:
        print("Skipping Brush 3DGS (download brush-app-x86_64-pc-windows-msvc.zip into tools/brush/ to enable).")

    print("\nScan-Your-Own-Home pipeline complete! Launch with: python scripts/home_os_server.py 8765")


if __name__ == "__main__":
    main()
