from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

repo_root = Path(SPECPATH).resolve().parents[1]

analysis = Analysis(
    [str(repo_root / "packaging" / "windows" / "launcher.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
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
bundle = COLLECT(
    exe, analysis.binaries, analysis.datas, strip=False, upx=False,
    upx_exclude=[], name="Smart Reels Studio",
)
