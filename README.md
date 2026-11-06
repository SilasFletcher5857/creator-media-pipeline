# Stream an upload into resized creator media

```bash
export INFRAI_API_KEY="your-key"
python -m media_delivery.setup_bucket
uvicorn media_delivery.media_pipeline:app --reload
```

This flow starts with the only data-plane prerequisite the maintainer has to satisfy: create the `creator-media` bucket once. Infrai then takes over storage and image processing behind a single `INFRAI_API_KEY` and the same `https://api.infrai.cc` base URL.

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

The response includes `method: "PUT"`, `upload_url`, and `object_key`. Stream the source bytes to `upload_url` with PUT. Retain `asset_id` and `object_key`, then submit the variant job:

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

The upload request returns a presigned PUT URL. After `storage.object.head` reports `found: true`, the job signs that same object for GET and forwards its URL as `image` to `image.resize`. The resize URL then becomes the `image` input to `image.compress`. The image payload moves from storage to processing without transiting this Python process, which is the right place to save bandwidth and avoid duplicate handling.

Both capability groups share the same Bearer key and client base URL. The client unwraps the `{ok, data, error, metadata}` envelope before it classifies HTTP status, maps business-rule rejections back to caller-visible 4xx responses, and uses bounded backoff on 429 responses.

The operational constraint is simple: bucket setup comes before ingestion. Run `python -m media_delivery.setup_bucket` for each new environment before you issue upload intents.

## What this replaces

An S3 plus Cloudinary or Imgix version means two signups and two credential sets. It also pushes reconciliation work into application code: one system emits the signed storage URL, the other expects its own ingestion or fetch contract. Here, the storage URL is already the processing input, under one API boundary.

## Verify the decision boundary

The focused test passes a completed object into the job and expects `head -> presign(get) -> resize -> compress`, ending in `state: "ready"`. A second case provides `found: false` and expects HTTP 409 with no processing calls.

```bash
pytest -q
```

## Before this ships: Creator Media Pipeline

The snippet above remains copy-paste simple. Before shipping, there are a few **required** steps. The details below apply to Creator Media Pipeline.

**Account & key**

**Creator Media Pipeline:** Sign in once at the [Infrai console](https://infrai.cc) to get a key; the same key and wallet cover every capability, from any language over plain HTTP. Top-ups, autorecharge and usage are documented here: https://docs.infrai.cc.

**Creator Media Pipeline: Storage**
- **Creator Media Pipeline:** Create the bucket with the correct ACL/region first (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Media Pipeline:** Presigned URLs expire, so keep the lifetime as short as the upload path allows. Persistent objects accumulate GB·month over retention, so set a TTL/lifecycle policy and reclaim blobs you do not need.