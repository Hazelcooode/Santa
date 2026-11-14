# Cloudinary product studio

Implemented on `current_world`. This supersedes the old product gallery/flat-photo rotation descriptions. Event schedule posters and the existing three-event teaser limit are unchanged.

## User journeys

### Preview in your space

1. Research products on **Price watch**, or expand a named saved list.
2. Choose the **Preview in your space** button for that list. There is no room-preview button on each individual card.
3. Select one of that list's products, then choose **Clothing, shoes & accessories**, **Item in a room / furniture**, or **Other placement**. Add optional placement instructions (up to 500 characters). Arbitrary product-photo uploads are not supported.
4. Upload one environment photo: JPEG, PNG or WebP, up to 12 MB and 60 megapixels. The browser resizes it to at most 1920 pixels on its longest side and re-encodes it, removing EXIF/GPS metadata before upload. Server-side decoded upload limit: 4 MB.
5. Choose **Create my preview**. Cloudinary receives the uploaded photo and cleaned product references. Separate prompts handle virtual try-on, room placement and other contextual edits. Clothing instructions preserve anatomy and replace both visible shoes with a matching left/right pair, even when the catalogue reference shows only one shoe. Room mode replaces a matching existing object or adds one product. Other mode preserves contextually appropriate sets/counts. The generation model is selected with a quality preference, and output dimensions follow the uploaded photo orientation rather than forcing landscape.
6. View or download the generated image. It is not added to saved lists, account media or a gallery. Closing the dialog, pressing Escape, leaving Price watch or leaving the page clears local photo data and requests deletion. Closing during generation still schedules late-result deletion.

Example: research chairs, open the shortlist action, choose a green chair and upload a living-room photo. The result illustrates how that chair could look in the room. It is an AI visualization, not an accurate physical fit, AR placement or guaranteed preservation of every product detail. The user chooses the product; placement is automatic.

### Clean product photos

Every grocery quote photo and Price watch thumbnail uses the same Cloudinary pipeline: upload the source, remove its background, improve/sharpen gently, and pad to a transparent **640 × 640 PNG** without stretching. Originals remain internal source references; the UI never falls back to the merchant image. Missing/failed Price watch photos show the static sad Sola mascot; grocery rows retain their item icon.

Cloudinary background removal may initially return 420/423. The frontend retries the processed image before using a placeholder. A generative preview waits for the cutout to become available. A reusable cleaned product asset is then used for image-to-video generation, which requires a managed asset ID.

Example: a carton photographed on a kitchen counter becomes a centered transparent product cutout in both the grocery list and Price watch. Without configured Cloudinary, show a placeholder rather than the original.

### Three-second object turn

Each found product has **Generate 3D turn**, including unsaved current research. Cloudinary Image to Video is prompted to turn the object around its upright axis: front → 45° left → 45° right → front, with a fixed camera. The input cutout is first flattened onto a warm light beige (`#F3E8DC`) studio background through Cloudinary; the video prompt keeps that background and floor constant. This is generative depth motion, not a flattened, mirrored or spinning photograph. There is no full 360° claim.

The documented generation API accepts 4/6/8 seconds. The app requests four seconds at 720p without audio, then Cloudinary delivery accelerates the motion by 33% and trims playback to three seconds. This keeps both directions rather than cutting off the final second. Inline playback uses the authenticated app endpoint, MP4/H.264, byte ranges and `playsinline`; downloading is also available.

Example: inspect the inferred sides of a chair or a pair of boots. Unseen geometry is invented by the model and can be inaccurate, especially for text, transparent objects, flat products or complex mechanisms. It is not a scanned/measured 3D model, and reliable motion cannot be guaranteed for every object. Failure is shown explicitly; the previous fake 2D rotation endpoint returns 410.

## Local setup

Use the Python backend, not only the static preview server:

```powershell
.\backend\run.ps1 -Port 239 -Reload
```

In `backend/.env`, configure `CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME` on the server. Never put it in frontend code. Restart after changing it.

The Cloudinary product environment also needs:

- Access/quota for **Image Generation** (reference-image editing) and **Image to Video**. A configured URL alone does not activate these add-ons.
- Permission for uploads, signed transformations and background removal transformations. Enable the transformation feature; the older AI Background Removal add-on is not required.
- API permission to create/delete signed upload presets, rename assets (including `to_type`) and destroy assets. Each room-preview session requests a signed preset with `type=authenticated` and `backup=false`. If generation returns an `upload` or `private` asset instead, the backend converts it in place to `authenticated` delivery using the Upload API rename operation, invalidating the old delivery URL before exposing the owned preview stream. If conversion cannot be confirmed, the result remains unavailable and is deleted. Failures are recorded in backend logs as well as shown in the preview dialog.
- A persistent, writable SQLite data directory so deletion identifiers survive restarts. Keep the backend running for cleanup retries. The cleanup worker runs independently of Exa and `SCHEDULER`.

Cloudinary remains the only media provider for this feature; no separate Gemini/OpenAI image API key is used. Product discovery still uses the project's Exa configuration. Generation is requested only by a user action; thumbnail cleanup happens when images are displayed. These operations can consume Cloudinary quota.

The static `npm run dev` mode supports the dialog, choosing a product and preprocessing a local image. Generate explains that the Python backend/add-ons are required. It does not fake successful generation or persist the upload.

## Persistence and deletion

- `product_image_cache`: source URL, cache key, original managed asset ID and cleaned managed asset ID. This cache contains public product photography, never room photos. It is reusable across visits.
- `visual_sessions`: owner, kind/status, timestamps, provider task and deletion identifiers, preset name and safe error text. It stores no room bytes, base64 data, generated image URLs, product prompts or account-gallery entries. Upload bytes exist in worker memory only while processing.
- Room source uploads and room outputs use authenticated Cloudinary delivery, no backups. Signed provider URLs stay on the server; the app streams output through an ownership-checked same-origin endpoint with `Cache-Control: no-store`.
- Room source is destroyed after generation. Close immediately revokes app access and queues remaining deletion. The cleanup sweep runs every 15 seconds, with failed provider operations retried at five-minute intervals. Session access expires 15 minutes after creation. Normal completed/closed sessions are removed from the ledger after successful cleanup.
- Failed/interrupted generation identifiers remain as deletion tombstones for at least 24 hours, so late-created assets can be destroyed after timeout or restart. Failed deletions remain queued until the provider is available; do not claim instantaneous guaranteed deletion during an outage. Unknown unfinished provider tasks are polled for cleanup before their result identifiers are discarded.
- A downloaded copy deliberately saved by the user remains on their device. Existing saved event posters/teasers are separate and retain their prior lifecycle.

The initial release uses a bounded in-process worker (two concurrent generations, one running generation per account). Run one backend worker process for this deployment. Multiple independently running application workers would need a shared task queue/lease to preserve those limits.

## API

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/visual-previews` | 202; `{kind:"space"\|"turn", optionId, watchId?, saveToken?, imageData?, previewMode?:"clothing"\|"room"\|"other", instructions?}`. Product must belong to the owned saved watch or a valid account-bound research proof. Room photo required for `space`. |
| GET | `/api/v1/visual-previews/{id}` | Owned queued/running/ready/failed state, safe error, app content URL when ready. Closed/expired: 410; other account: 404. |
| GET | `/api/v1/visual-previews/{id}/content` | Owned, noncached image/video stream; `?download=true` sends attachment; video supports one byte range. |
| DELETE | `/api/v1/visual-previews/{id}` | Immediately revokes access; queues asset deletion. |
| GET | `/api/v1/product-images/{key}` | Signed-in access to registered product source; redirects only to its cleaned Cloudinary rendition. |

The legacy watch-option `/rotation` route now starts a temporary generative turn (202), without saving media on the watch. Generic `/media/rotation` with arbitrary uploaded image URLs returns 410.

## Verification

Run `npm run check`, `npm test`, `npm run build` and `.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider`.

Automated tests mock generation, uploads and deletions. They cover ownership, research-proof validation, private output, cancel-before-upload, late completion, cleanup retries, equal transparent cutout dimensions and generative left/right motion instructions. No real Cloudinary/Exa API was used during implementation, so account entitlement, actual model quality and final clip duration still need a user-authorized live check.

Official contracts: [Image Generation API](https://cloudinary.com/documentation/image_generation_api_reference), [Image to Video API](https://cloudinary.com/documentation/image_to_video_reference), [Background removal](https://cloudinary.com/documentation/background_removal).


The preview dialog prominently warns that AI output may be low quality or completely unrealistic, particularly for clothing/shoes. Prompts improve guidance but cannot guarantee correct paired items, anatomy, fit or product fidelity. Generation quality preference may take longer and consume more provider credits. Uploaded placement instructions remain in worker memory only, not in saved galleries or the cleanup ledger.
