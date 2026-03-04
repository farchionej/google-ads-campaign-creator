# Google Ads Image Asset Guide

Quick reference for preparing images for Google Ads campaigns (PMax and Display).

## Required Dimensions

| Type | Prefix | Aspect Ratio | Min Pixels | Recommended | Max File Size |
|------|--------|-------------|------------|-------------|---------------|
| Landscape | `ls_` | 1.91:1 | 600x314 | 1200x628 | 5MB |
| Square | `sq_` | 1:1 | 300x300 | 1200x1200 | 5MB |
| Portrait | `pt_` | 4:5 | 480x600 | 960x1200 | 5MB |
| Logo (landscape) | `logo_` | 4:1 | 512x128 | 1200x300 | 5MB |
| Logo (square) | `logo_sq_` | 1:1 | 128x128 | 1200x1200 | 5MB |

## Minimum Required Per Asset Group

- **1 landscape image** (1.91:1)
- **1 square image** (1:1)
- **1 logo** (any format)

## Recommended Per Asset Group

- 3-5 landscape images
- 3-5 square images
- 1-2 portrait images
- 1 landscape logo + 1 square logo

## File Naming Convention

Use the aspect ratio prefix + descriptive name:
```
ls_exterior.jpg        # Landscape exterior shot
ls_patio_evening.jpg   # Landscape patio at night
sq_food_1.jpg          # Square food photo
sq_cocktail.jpg        # Square cocktail shot
pt_interior.jpg        # Portrait interior
logo_main.png          # Main logo (landscape)
logo_sq_main.png       # Square logo variant
```

## Format Requirements

- **Formats**: PNG or JPG (PNG preferred for logos)
- **Max file size**: 5MB per image
- **Color space**: sRGB
- **No text overlays** covering more than 20% of the image
- **No borders, watermarks, or frames**

## Quality Tips

- Use high-resolution source images (minimum 2x the required pixels)
- Food photos: well-lit, appetizing, professionally styled
- Interior/exterior: capture the ambiance, avoid empty rooms
- Avoid stock photos — real restaurant photos convert better
- Logos: use transparent PNG backgrounds
- Test with dark and light backgrounds (Google places assets on various surfaces)

## Where to Source Images

1. **Client's Instagram** — Best source for authentic food/ambiance photos
   - Download with `python3 tools/batch_instagram_download.py --client {key} --count 10`
2. **Client's website** — Often has professional photography
3. **GBP photos** — Already uploaded to Google Business Profile
4. **Jay Street stock** — `.claude/shared/google-ads-creative/stock/` for logos

## Workflow

1. Collect images from sources above
2. Rename with prefix convention
3. Place in `clients/{key}/assets/google-ads/images/`
4. System validates dimensions before upload
5. Agent base64-encodes and uploads via API
