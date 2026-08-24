# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

block_cipher = None

project_root = Path(SPECPATH)
frontend_dist = project_root / "src" / "frontend" / "dist"
if not (frontend_dist / "index.html").is_file():
    raise SystemExit(
        "Built frontend not found. Run `npm --prefix src/frontend run build` first."
    )

bundled_models = project_root / "bundled_models" / "models"
if not bundled_models.is_dir():
    raise SystemExit(
        "Bundled AI models not found. Run `uv run python scripts/bundle_models.py` first."
    )

a = Analysis(
    ["launcher.pyw"],
    pathex=[str(project_root)],
    binaries=collect_dynamic_libs("sqlite_vec")
    + collect_dynamic_libs("ctranslate2")
    + collect_dynamic_libs("av"),
    datas=[
        (str(frontend_dist), "frontend"),
        ("src/aac_app/data/ngrams", "src/aac_app/data/ngrams"),
        (
            "src/aac_app/config/companion_templates",
            "src/aac_app/config/companion_templates",
        ),
        (str(bundled_models), "models"),
        (".env.example", "."),
    ]
    + collect_data_files("faster_whisper"),
    hiddenimports=collect_submodules("src.aac_app")
    + collect_submodules("src.api")
    + collect_submodules("faster_whisper")
    + collect_submodules("kokoro_onnx"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
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
