from uuid import UUID

from fastapi.testclient import TestClient

from media_delivery.media_pipeline import app, get_infrai


class RecordedInfrai:
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.calls: list[tuple] = []

    def head_object(self, bucket: str, key: str) -> dict:
        self.calls.append(("head", bucket, key))
        return {"found": self.found}

    def presign_object(self, bucket: str, key: str, op: str, idempotency_key: str, content_type=None, max_bytes=None) -> dict:
        self.calls.append(("presign", bucket, key, op, idempotency_key, content_type, max_bytes))
        return {"url": f"https://signed.example/{op}"}

    def resize_image(self, image: str, width: int, height: int, fit: str, format: str) -> dict:
        self.calls.append(("resize", image, width, height, fit, format))
        return {"url": "https://media.example/resized.webp"}

    def compress_image(self, image: str) -> dict:
        self.calls.append(("compress", image))
        return {"url": "https://media.example/final.webp"}


def test_uploaded_asset_flows_directly_into_resize_then_compress() -> None:
    fake = RecordedInfrai()
    app.dependency_overrides[get_infrai] = lambda: fake
    asset_id = UUID("7d264927-d933-48bb-a532-f21d84db528c")

    with TestClient(app) as client:
        response = client.post(
            "/jobs/variants",
            json={
                "asset_id": str(asset_id),
                "object_key": "creators/alex/7d264927/photo.png",
                "width": 1200,
                "height": 800,
                "fit": "cover",
                "format": "webp",
            },
        )

    app.dependency_overrides.clear()
    assert response.status_code == 201
    assert response.json() == {
        "asset_id": str(asset_id),
        "state": "ready",
        "delivery_url": "https://media.example/final.webp",
    }
    assert fake.calls[1][3] == "get"
    assert fake.calls[2][1] == "https://signed.example/get"
    assert fake.calls[3][1] == "https://media.example/resized.webp"


def test_processing_waits_until_the_upload_exists() -> None:
    fake = RecordedInfrai(found=False)
    app.dependency_overrides[get_infrai] = lambda: fake

    with TestClient(app) as client:
        response = client.post(
            "/jobs/variants",
            json={
                "asset_id": "7d264927-d933-48bb-a532-f21d84db528c",
                "object_key": "creators/alex/7d264927/photo.png",
                "width": 1200,
                "height": 800,
            },
        )

    app.dependency_overrides.clear()
    assert response.status_code == 409
    assert [call[0] for call in fake.calls] == ["head"]

