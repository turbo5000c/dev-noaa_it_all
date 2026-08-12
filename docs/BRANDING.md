# Branding & icons

Everything about where this integration's icon and logo come from, and — importantly — why the
HACS store list still shows a placeholder no matter what we do here.

Read this before touching anything under `custom_components/noaa_it_all/brand/`. Three separate
attempts to "fix" the HACS icon have already been made and reverted; all of them were chasing a
problem that does not live in this repository.

---

## How brand images work (Home Assistant 2026.3+)

Since HA 2026.3, custom integrations ship their own brand images. No external repository is
involved. See the [brands proxy API announcement][announce].

```
custom_components/noaa_it_all/
├── manifest.json
└── brand/
    ├── icon.png            256x256
    ├── icon@2x.png         512x512
    ├── logo.png            1108x256   wordmark lockup
    ├── logo@2x.png         2216x512
    ├── dark_logo.png       1108x256   pale text for dark themes
    └── dark_logo@2x.png    2216x512
```

Home Assistant serves these at `/api/brands/integration/{domain}/{image}`, and **local files take
priority over the brands CDN**.

### The folder must be named exactly `brand`

In HA core, `homeassistant/loader.py` defines integration branding as, literally:

```python
return "brand" in self._top_level_files
```

Singular, no alternatives. Renaming it to `brands/` does not "match the CDN layout" — it makes HA
stop serving our images entirely. This was tried in `a3679e8` and reverted in `ffc7a1d`.

### Fallback chain

From `homeassistant/components/brands/const.py`, applied to local lookups too:

```
dark_icon.png    -> icon.png
dark_logo.png    -> dark_icon.png    -> logo.png    -> icon.png
dark_icon@2x.png -> icon@2x.png      -> icon.png
dark_logo@2x.png -> dark_icon@2x.png -> logo@2x.png -> logo.png -> icon.png
```

Two consequences we rely on:

- **No `dark_icon.png` is needed.** The icon is a navy disc with a pale ring — it reads on light
  and dark backgrounds alike. A dark copy would be byte-identical, and the chain already resolves
  to `icon.png`. It was deleted for exactly this reason.
- **A dark wordmark needs both `dark_logo.png` and `dark_logo@2x.png`.** The logo is a wordmark
  whose navy text disappears on a dark card, so real dark artwork is required. Ship only the 1x and
  the @2x request falls through to the light `logo@2x.png`.

`tests/test_manifest.py::TestBrandAssets` enforces the dimensions, PNG format (8-bit RGBA,
non-interlaced), transparent corners, and that dark variants are not byte-copies.

---

## Why the HACS store list shows "icon not available"

**This is an upstream HACS bug. Nothing in this repository can fix it.**

HACS's frontend renders that list icon through `brandsUrl()` from its **pinned**
`homeassistant-frontend` submodule, which still resolves to the legacy CDN:

```
https://brands.home-assistant.io/_/noaa_it_all/icon.png
```

That CDN is backed by the [`home-assistant/brands`][brands] repository, where `noaa_it_all` does
not exist. No file in this repo feeds that URL.

**And it cannot be added.** `home-assistant/brands` runs
`.github/workflows/close-new-custom-integrations.yml` on `pull_request_target` for
`custom_integrations/**`, which auto-comments and auto-closes any PR that adds a new custom
integration folder. Its README now labels `custom_integrations/` a "Legacy folder".

So the situation is: the mechanism HACS reads from is closed to us, and the mechanism that is open
to us (local `brand/`) is one HACS does not read yet. Our icon renders correctly everywhere in
Home Assistant itself — Settings → Devices & Services, the integration page, device pages — and
only the HACS store list is affected.

### Tracking

All open as of August 2026. [hacs/frontend#937][pr937] is the one that would actually ship the fix.

| Link | What it is |
| --- | --- |
| [hacs/integration#5171][i5171] | HACS dashboard doesn't show local brand icons (HA 2026.3+) |
| [hacs/integration#5223][i5223] | Downloads panel shows "icon not available" for inline brand icons |
| [hacs/frontend#937][pr937] | Bump the submodule, use the `/api/brands/...` proxy path |
| [hacs/integration#5388][pr5388] | HACS-side icon endpoint that reads the local `brand/` folder |

HACS frontend's last release is `20250128065759` — January 2025. Nothing has shipped in 2026, so
expect this to sit until a new frontend bundle is cut.

The only useful action is a "still affected" note or a 👍 on **#937**. Do not open a fifth issue.

---

## DO NOT TRY

Each of these has been attempted or considered, and each is wrong:

| Don't | Why |
| --- | --- |
| Add/move `icon.png` at the repo root to fix the HACS list icon | Nothing reads it for that. Tried in `8ca08d9`. The file is kept only as the README header image source. |
| Rename `brand/` to `brands/` | Breaks `has_branding` in HA core; HA stops serving our icons. Tried in `a3679e8`, reverted in `ffc7a1d`. |
| Submit `custom_integrations/noaa_it_all` to `home-assistant/brands` | Auto-closed by a bot on open. |
| Assume HACS default-store membership grants a CDN icon | It does not. The list icon comes from the brands repo, which is closed to new custom integrations. |
| Add `dark_icon.png` or `dark_icon@2x.png` | The fallback chain already resolves them to the theme-agnostic icon. A byte-identical copy fails `test_dark_variants_are_not_copies`. |
| Point README images at `github.com/.../blob/...` | That URL serves an HTML page, not an image. Use `raw.githubusercontent.com`. Guarded by `TestReadmeImages`. |

---

## Regenerating the wordmark

`logo.png`, `logo@2x.png`, `dark_logo.png` and `dark_logo@2x.png` are a lockup: the icon on the
left, "NOAA It All" set in Liberation Sans Bold to its right, trimmed to content.

Brand colors sampled from `brand/icon.png`:

| Role | Hex | Used for |
| --- | --- | --- |
| Navy (icon body) | `#0d2e70` | wordmark text in `logo.png` |
| Pale blue (icon ring) | `#c0e4f5` | wordmark text in `dark_logo.png` |

The @2x files are rendered first at 512px tall and the 1x files are produced by halving them, so
the 2x relationship is exact. If you change the art, update the pinned dimensions in
`_BRAND_ASSETS` in `tests/test_manifest.py` to match.

---

## Verifying it actually works

In a live HA instance, the definitive check is the API. Two traps:

1. The endpoint authenticates even though `requires_auth` is `False` — an unauthenticated browser
   hit returns **403** and looks broken when it isn't. Use a long-lived access token.
2. Without `?placeholder=no`, a miss returns the generic CDN placeholder with a **200**.

```bash
curl -s -o /dev/null -w '%{http_code} %{content_type} %{size_download}\n' \
  -H "Authorization: Bearer <LONG_LIVED_TOKEN>" \
  "http://homeassistant.local:8123/api/brands/integration/noaa_it_all/logo.png?placeholder=no"
```

- `200 image/png <byte count matching brand/logo.png>` — correct, served from `brand/`.
- `404` — nothing resolved: `brand/` missing or misnamed, HA below 2026.3, or no restart since the
  files landed.
- `401` / `403` — token problem, not a branding problem.

Check `dark_icon.png` too: it must return the byte count of `icon.png`, proving the fallback chain
resolved rather than 404'ing.

In the UI: Settings → Devices & Services → the NOAA It All card. Hard-refresh — HA caches brand
images on disk for 30 days and browsers cache them as well. Toggle the HA theme to check the dark
logo.

[announce]: https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/
[brands]: https://github.com/home-assistant/brands
[i5171]: https://github.com/hacs/integration/issues/5171
[i5223]: https://github.com/hacs/integration/issues/5223
[pr937]: https://github.com/hacs/frontend/pull/937
[pr5388]: https://github.com/hacs/integration/pull/5388
