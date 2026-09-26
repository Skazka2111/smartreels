import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

repo_root = Path(SPECPATH).resolve().parents[1]
ffmpeg_path = Path(os.environ["SMART_REELS_FFMPEG"]).resolve()
ffprobe_path = Path(os.environ["SMART_REELS_FFPROBE"]).resolve()

analysis = Analysis(
    [str(repo_root / "packaging" / "macos" / "launcher.py")],
    pathex=[str(repo_root / "src")],
    binaries=[(str(ffmpeg_path), "."), (str(ffprobe_path), ".")],
    datas=(
        collect_data_files("smart_reels")
        + collect_data_files("cv2", includes=["data/*.xml"])
    ),
    hiddenimports=["cv2", "numpy"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=1,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True,
    name="Smart Reels Studio", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
)
bundle_files = COLLECT(
    exe, analysis.binaries, analysis.datas, strip=False, upx=False,
    upx_exclude=[], name="Smart Reels Studio",
)
app = BUNDLE(
    bundle_files,
    name="Smart Reels Studio.app",
    bundle_identifier="pw.proaistudio.smart-reels-studio",
    info_plist={
        "CFBundleDisplayName": "Smart Reels Studio",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "NSHighResolutionCapable": True,
    },
)
