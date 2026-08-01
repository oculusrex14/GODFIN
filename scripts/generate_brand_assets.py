#!/usr/bin/env python3
"""Generate GODFIN brand assets from the owner-approved Vault Dial artwork.

The source PNG is committed byte-for-byte from the owner's logo pack.  The
UI mark is a lossless crop of that source; only platform icon derivatives are
resampled and composited onto the approved deep-navy app-icon background.
"""

from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path
import sys

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRAND_ROOT = PROJECT_ROOT / "shared" / "brand"
SOURCE = BRAND_ROOT / "godfin-vault-dial-source.png"
MARK = BRAND_ROOT / "godfin-vault-dial-mark.png"
APP_ICON = BRAND_ROOT / "godfin-app-icon.png"

SOURCE_SHA256 = "bc12b6bf74d3867e999c147fc90f7612d02efb4402cacea0cf576d1f76345a96"
MARK_CROP = (383, 75, 1151, 843)
DEEP_NAVY = (11, 29, 51, 255)

COPIES = {
    PROJECT_ROOT / "frontend" / "public" / "godfin-vault-dial.png": MARK,
    PROJECT_ROOT / "website" / "public" / "godfin-vault-dial.png": MARK,
    PROJECT_ROOT / "desktop" / "assets" / "icon.png": APP_ICON,
    PROJECT_ROOT / "desktop" / "assets" / "icons" / "1024x1024.png": APP_ICON,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def make_mark(source: Image.Image) -> Image.Image:
    """Return the approved square mark without resampling its pixels."""
    return source.crop(MARK_CROP)


def make_app_icon(mark: Image.Image) -> Image.Image:
    """Place the approved mark on the app-icon treatment shown in the pack."""
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    background = Image.new("RGBA", canvas.size, DEEP_NAVY)
    mask = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((24, 24, 1000, 1000), radius=210, fill=255)
    canvas.alpha_composite(Image.composite(background, Image.new("RGBA", canvas.size), mask))

    rendered_mark = mark.resize((850, 850), Image.Resampling.LANCZOS)
    canvas.alpha_composite(rendered_mark, ((1024 - 850) // 2, (1024 - 850) // 2))
    return canvas


def expected_assets() -> dict[Path, bytes]:
    source_data = SOURCE.read_bytes()
    actual_source_sha = sha256(source_data)
    if actual_source_sha != SOURCE_SHA256:
        raise RuntimeError(
            "Owner-approved source artwork changed: "
            f"expected {SOURCE_SHA256}, got {actual_source_sha}"
        )

    with Image.open(io.BytesIO(source_data)) as image:
        source = image.convert("RGBA")
        if source.size != (1536, 1024):
            raise RuntimeError(f"Unexpected source dimensions: {source.size}")
        mark = make_mark(source)
        app_icon = make_app_icon(mark)

    assets: dict[Path, bytes] = {
        MARK: png_bytes(mark),
        APP_ICON: png_bytes(app_icon),
    }
    for destination, asset_source in COPIES.items():
        assets[destination] = assets[asset_source]

    ico = io.BytesIO()
    app_icon.save(
        ico,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    assets[PROJECT_ROOT / "desktop" / "assets" / "icon.ico"] = ico.getvalue()

    icns = io.BytesIO()
    app_icon.save(icns, format="ICNS")
    assets[PROJECT_ROOT / "desktop" / "assets" / "icon.icns"] = icns.getvalue()
    return assets


def verify(assets: dict[Path, bytes]) -> list[str]:
    errors = []
    for path, expected in assets.items():
        if not path.is_file():
            errors.append(f"missing: {path.relative_to(PROJECT_ROOT)}")
            continue
        actual = path.read_bytes()
        if actual != expected:
            errors.append(
                f"mismatch: {path.relative_to(PROJECT_ROOT)} "
                f"(expected {sha256(expected)}, got {sha256(actual)})"
            )
    return errors


def write(assets: dict[Path, bytes]) -> None:
    for path, data in assets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed derivatives without changing files",
    )
    args = parser.parse_args()

    assets = expected_assets()
    if args.check:
        errors = verify(assets)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print(f"Verified {len(assets)} owner-approved GODFIN brand assets.")
        return 0

    write(assets)
    print(f"Generated {len(assets)} GODFIN brand assets from {SOURCE.relative_to(PROJECT_ROOT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
