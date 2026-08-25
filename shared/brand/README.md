# GODFIN owner-approved brand source

`godfin-vault-dial-source.png` is the exact owner-supplied Vault Dial artwork
from `/Users/oculus/Projects/GODFIN/logo pack/ddf05cac-8474-4587-912d-a3c2e9bceb08.png`.

- Approved source SHA-256: `02304401ded78fbc7e59c661f4fc6b39b85667562df09ed0a5587f8c0b32b4a9`
- Approved source dimensions: `1536 × 1024` RGBA
- `godfin-vault-dial-mark.png` is a lossless `768 × 768` crop using source
  coordinates `(395, 130, 1163, 898)`. The logo pixels are not redrawn.
- `godfin-app-icon.png` uses that approved mark on the deep-navy app-icon
  treatment shown in the supplied logo board.

Regenerate or verify every committed derivative with:

```bash
backend/venv/bin/python scripts/generate_brand_assets.py
backend/venv/bin/python scripts/generate_brand_assets.py --check
```

Do not replace the source or redraw the Vault Dial. A changed source checksum
causes the verifier to fail deliberately.
