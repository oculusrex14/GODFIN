# GODFIN owner-approved brand source

`godfin-vault-dial-source.png` is the exact owner-supplied Vault Dial artwork
from `/Users/oculus/Projects/GODFIN/logo pack/ddf05cac-8474-4587-912d-a3c2e9bceb08.png`.

- Approved source SHA-256: `bc12b6bf74d3867e999c147fc90f7612d02efb4402cacea0cf576d1f76345a96`
- Approved source dimensions: `1536 × 1024` RGBA
- `godfin-vault-dial-mark.png` is a lossless `768 × 768` crop using source
  coordinates `(383, 75, 1151, 843)`. The logo pixels are not redrawn.
- `godfin-app-icon.png` uses that approved mark on the deep-navy app-icon
  treatment shown in the supplied logo board.

Regenerate or verify every committed derivative with:

```bash
backend/venv/bin/python scripts/generate_brand_assets.py
backend/venv/bin/python scripts/generate_brand_assets.py --check
```

Do not replace the source or redraw the Vault Dial. A changed source checksum
causes the verifier to fail deliberately.
