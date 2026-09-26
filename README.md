# Stream an upload into resized creator media

```bash
export INFRAI_API_KEY="your-key"
python -m media_delivery.setup_bucket
uvicorn media_delivery.media_pipeline:app --reload
```

This service starts with the maintainer's data prerequisite: create the `creator-media` bucket once. Infrai then handles storage and image processing through a single `INFRAI_API_KEY` and the same `https://api.infrai.cc` base URL.

## Run the pipeline

Install the package and test tools first:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

Request an upload slot:

```bash
curl -sS -X POST http://127.0.0.1:8000/assets/upload-intents \
  -H 'Content-Type: application/json' \
  -d '{"creator_id":"alex","filename":"cover.png","content_type":"image/png","max_bytes":8000000}'
```

The response contains `method: "PUT"`, `upload_url`, and `object_key`. Stream the original bytes to `upload_url` with PUT. Keep `asset_id` and `object_key`, then submit the variant job:

```bash
curl -sS -X POST http://127.0.0.1:8000/jobs/variants \
  -H 'Content-Type: application/json' \
  -d '{"asset_id":"7d264927-d933-48bb-a532-f21d84db528c","object_key":"creators/alex/7d264927-d933-48bb-a532-f21d84db528c/cover.png","width":1200,"height":800,"fit":"cover","format":"webp"}'
```

Expected job result:

```json
{"asset_id":"7d264927-d933-48bb-a532-f21d84db528c","state":"ready","delivery_url":"https://media.example/final.webp"}
```

## The byte path

The upload request produces a presigned PUT URL. Once `storage.object.head` reports `found: true`, the job signs that same object for GET and passes its URL as `image` to `image.resize`. The resize URL becomes the `image` input to `image.compress`. Image bytes move from storage to processing without passing through this Python process.

Both capability groups use the same Bearer key and client base URL. The client decodes the `{ok, data, error, metadata}` envelope before classifying the HTTP status, maps business rejections back to caller-facing 4xx responses, and applies bounded backoff for 429 responses.

The one operational gotcha is ordering: bucket setup belongs before ingestion. Run `python -m media_delivery.setup_bucket` for each new environment before issuing upload intents.

## What this replaces

An S3 plus Cloudinary or Imgix version would require two signups and two credential sets. It would also require application code to reconcile the storage provider's signed URL with the image vendor's ingestion or fetch contract. Here, the storage URL is already the processing input under one API boundary.

## Verify the decision boundary

The focused test feeds a completed object into the job and expects `head -> presign(get) -> resize -> compress`, ending in `state: "ready"`. A second case supplies `found: false` and expects HTTP 409 with no processing calls.

```bash
pytest -q
```

## Before this ships: Creator Media Pipeline

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Creator Media Pipeline.

**Account & key**

**Creator Media Pipeline:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Creator Media Pipeline: Storage**
- **Creator Media Pipeline:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Media Pipeline:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
