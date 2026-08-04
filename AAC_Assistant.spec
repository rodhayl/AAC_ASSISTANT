# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

block_cipher = None

project_root = Path(SPECPATH)
frontend_dist = project_root / "src" / "frontend" / "dist"
if not (frontend_dist / "index.html").is_file():
    raise SystemExit(
        "Built frontend not found. Run `npm --prefix src/frontend run build` first."
    )

a = Analysis(
    ["launcher.pyw"],
    pathex=[str(project_root)],
    binaries=collect_dynamic_libs("sqlite_vec"),
    datas=[
        (str(frontend_dist), "frontend"),
        ("src/aac_app/data/ngrams", "src/aac_app/data/ngrams"),
        (
            "src/aac_app/config/companion_templates",
            "src/aac_app/config/companion_templates",
        ),
        (".env.example", "."),
    ],
    hiddenimports=collect_submodules("src.aac_app") + collect_submodules("src.api"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Optional voice support is installed and downloaded after packaging.
        "faster_whisper",
        "ctranslate2",
        "av",
        "torch",
        "torchaudio",
        "torchvision",
        # Development/test tooling never ships in the release.
        "pytest",
        "pytest_cov",
        "ruff",
        "pip_audit",
        "coverage",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AAC_Assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AAC_Assistant",
)
