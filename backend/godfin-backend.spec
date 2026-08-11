# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

hiddenimports = collect_submodules("app")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("fastembed")
hiddenimports += [
    "google_auth_oauthlib.flow",
    "googleapiclient.discovery",
    "googleapiclient.errors",
]

datas = [
    (
        str(Path(SPECPATH).resolve().parent / "shared" / "entitlements.json"),
        "shared",
    ),
    (
        str(
            Path(SPECPATH).resolve().parent
            / "shared"
            / "license-entitlement-public-keys.json"
        ),
        "shared",
    ),
    (
        str(Path(SPECPATH).resolve().parent / "shared" / "model-registry.json"),
        "shared",
    ),
    (
        str(Path(SPECPATH).resolve().parent / "shared" / "model-registry.json.sig"),
        "shared",
    ),
    (
        str(Path(SPECPATH).resolve().parent / "shared" / "model-registry-public-key.txt"),
        "shared",
    ),
]
for package in ("matplotlib", "fastembed"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass
datas += copy_metadata("fastembed")

analysis = Analysis(
    ["desktop_entry.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "sentence_transformers",
        "tensorflow",
        "tkinter",
        "torch",
        "transformers",
    ],
    noarchive=False,
    optimize=1,
)

# google-api-python-client ships discovery documents for every Google API
# (~100 MB). GODFIN only needs Gmail's 148 KB document.
analysis.datas = [
    item
    for item in analysis.datas
    if (
        "googleapiclient/discovery_cache/documents/" not in item[0]
        or item[0].endswith("/gmail.v1.json")
    )
]
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="godfin-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="godfin-backend",
)
