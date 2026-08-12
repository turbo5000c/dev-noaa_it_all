# Branding & icons

Where this integration's icon and logo come from, and why the HACS store list shows a placeholder.

Read this before touching anything under `custom_components/noaa_it_all/brand/`. Three separate
attempts to fix the HACS icon have already been made and reverted.

---

## Two different systems, two different sources

This is the thing that makes the problem confusing. The icon you see **inside Home Assistant** and
the icon you see **in the HACS store list** come from completely different places.

| Where | Source | Status |
| --- | --- | --- |
| HA Settings → Devices & Services, integration/device pages | our local `custom_components/noaa_it_all/brand/` folder | works |
| HACS store / downloads list | the `home-assistant/brands` CDN, keyed on domain | shows placeholder |

Fixing one does nothing for the other.

---

## Local brand images (Home Assistant)

Since HA 2026.3, custom integrations ship their own brand images — see the
[brands proxy API announcement][announce]. HA serves them at
`/api/brands/integration/{domain}/{image}`, and local files take priority over the CDN.

```
custom_components/noaa_it_all/
├── manifest.json
└── brand/
    ├── icon.png         256x256
    ├── icon@2x.png      512x512
    ├── logo.png         768x256
    ├── logo@2x.png      1536x512
    ├── dark_icon.png    256x256
    └── dark_logo.png    768x256
```

### The folder must be named exactly `brand`

In HA core, `homeassistant/loader.py` defines integration branding as, literally:

```python
return "brand" in self._top_level_files
```

Singular, no alternatives. Renaming it to `brands/` to "match the CDN layout" makes HA stop serving
our images entirely. This was tried in `a3679e8` and reverted in `ffc7a1d`.

### Fallback chain

From `homeassistant/components/brands/const.py`, applied to local lookups too:

```
dark_icon.png    -> icon.png
dark_logo.png    -> dark_icon.png    -> logo.png    -> icon.png
dark_icon@2x.png -> icon@2x.png      -> icon.png
dark_logo@2x.png -> dark_icon@2x.png -> logo@2x.png -> logo.png -> icon.png
```

Note that `dark_icon.png` and `dark_logo.png` are currently byte-identical to their light
counterparts, so they are technically redundant — the chain would resolve to the same bytes if they
were absent. They are harmless; removing them is optional cleanup, not a fix for anything.

`tests/test_manifest.py::TestBrandAssets` enforces dimensions, PNG format (8-bit RGBA,
non-interlaced) and transparent corners.

---

## Why the HACS store list shows "icon not available"

HACS's frontend renders that list icon through `brandsUrl()` from its **pinned**
`homeassistant-frontend` submodule, which resolves to the legacy CDN:

```
https://brands.home-assistant.io/_/noaa_it_all/icon.png
```

That CDN is backed by the [`home-assistant/brands`][brands] repository. **`noaa_it_all` is not in
it** — `custom_integrations/noaa_it_all/` returns 404.

This is not HACS being broken in general. Other custom integrations show icons precisely because
they *are* in that repo. Verified examples:

| Domain | In `home-assistant/brands/custom_integrations/`? | Icon in HACS |
| --- | --- | --- |
| `alarmo` | yes — `icon.png`, `icon@2x.png` | shows |
| `frigate` | yes — full set incl. dark variants | shows |
| `noaa_it_all` | **no — 404** | placeholder |

Being in the HACS **default store** is a separate thing and we already are: `dawg-io/noaa_it_all`
is listed in [`hacs/default`][hacsdefault]. Default-store membership does not grant a CDN icon.

So the store-list icon depends on one thing only: **is the domain in `home-assistant/brands`?**

### Getting into the brands repo

This is the only thing that makes the HACS list icon work today, and it may or may not still be
open to us:

- The brands README now calls `custom_integrations/` a "Legacy folder" and points at the inline
  `brand/` mechanism.
- There is a `.github/workflows/close-new-custom-integrations.yml` that fires on
  `pull_request_target` for `custom_integrations/**` and auto-closes PRs which add a **new** folder
  (it detects "new" by all files in the folder having status `added`).
- However, the commit history shows new custom integrations still landing through spring 2026
  (Arctic Spa, Clausius, TP-Link Omada), with mid-2026 activity mostly moves to core and deletions.

**Conclusion: submitting `custom_integrations/noaa_it_all/` to `home-assistant/brands` is worth one
attempt.** It costs a single PR. If the bot auto-closes it, that answers the question definitively
and the fallback is waiting on HACS (below). Assets must meet their spec: `icon.png` 256x256,
`icon@2x.png` 512x512, optional `logo.png`/`logo@2x.png` landscape, trimmed of empty edge space,
and dark variants only if they genuinely differ (ours currently do not, so submit without them).

### The HACS-side fix, if brands stays closed

HACS has not implemented reading local `brand/` folders. Tracking, all open as of August 2026:

| Link | What it is |
| --- | --- |
| [hacs/integration#5171][i5171] | HACS dashboard doesn't show local brand icons (HA 2026.3+) |
| [hacs/integration#5223][i5223] | Downloads panel shows "icon not available" for inline brand icons |
| [hacs/frontend#937][pr937] | Bump the submodule, use the `/api/brands/...` proxy path |
| [hacs/integration#5388][pr5388] | HACS-side icon endpoint that reads the local `brand/` folder |

HACS frontend's last release is `20250128065759` — January 2025.

---

## DO NOT TRY

| Don't | Why |
| --- | --- |
| Add/move `icon.png` at the repo root to fix the HACS list icon | Nothing reads it for that. Tried in `8ca08d9`. The file is kept as the README header image source. |
| Rename `brand/` to `brands/` | Breaks `has_branding` in HA core; HA stops serving our icons. Tried in `a3679e8`, reverted in `ffc7a1d`. |
| Assume HACS default-store membership grants a CDN icon | It does not. We are already in `hacs/default` and still show the placeholder. |
| Point README images at `github.com/.../blob/...` | That URL serves an HTML page, not an image. Use `raw.githubusercontent.com`. Guarded by `TestReadmeImages`. |

---

## Verifying the local mechanism works

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

In the UI: Settings → Devices & Services → the NOAA It All card. Hard-refresh — HA caches brand
images on disk for 30 days and browsers cache them as well.

[announce]: https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/
[brands]: https://github.com/home-assistant/brands
[hacsdefault]: https://github.com/hacs/default/blob/master/integration
[i5171]: https://github.com/hacs/integration/issues/5171
[i5223]: https://github.com/hacs/integration/issues/5223
[pr937]: https://github.com/hacs/frontend/pull/937
[pr5388]: https://github.com/hacs/integration/pull/5388
