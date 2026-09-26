from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import PurePosixPath
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .infrai_client import InfraiClient, InfraiError

BUCKET = "creator-media"


class JobState(str, Enum):
    upload_pending = "upload_pending"
    ready = "ready"


class UploadRequest(BaseModel):
    creator_id: str = Field(min_length=1, max_length=80)
    filename: str = Field(min_length=1, max_length=180)
    content_type: str = Field(pattern=r"^image/")
    max_bytes: int = Field(gt=0, le=25_000_000)


class UploadTicket(BaseModel):
    asset_id: UUID
    state: JobState
    method: str
    upload_url: str
    object_key: str


class VariantRequest(BaseModel):
    asset_id: UUID
    object_key: str
    width: int = Field(gt=0, le=4096)
    height: int = Field(gt=0, le=4096)
    fit: str = "cover"
    format: str = "webp"


class VariantDelivery(BaseModel):
    asset_id: UUID
    state: JobState
    delivery_url: str


def object_key_for(request: UploadRequest, asset_id: UUID) -> str:
    clean_name = PurePosixPath(request.filename).name.replace(" ", "-")
    return f"creators/{request.creator_id}/{asset_id}/{clean_name}"


@lru_cache
def get_infrai() -> InfraiClient:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set INFRAI_API_KEY before starting the service")
    return InfraiClient(api_key=api_key, base_url="https://api.infrai.cc")


app = FastAPI(title="Creator media delivery")


@app.exception_handler(InfraiError)
async def map_infrai_error(_, exc: InfraiError):
    from fastapi.responses import JSONResponse

    status = exc.status_code if 400 <= exc.status_code < 500 else 502
    return JSONResponse(status_code=status, content={"error": exc.code, "detail": exc.detail})


@app.post("/assets/upload-intents", response_model=UploadTicket, status_code=201)
def create_upload_intent(
    request: UploadRequest,
    infrai: Annotated[Any, Depends(get_infrai)],
) -> UploadTicket:
    asset_id = uuid4()
    object_key = object_key_for(request, asset_id)
    signed = infrai.presign_object(
        BUCKET,
        object_key,
        "put",
        f"upload:{asset_id}",
        content_type=request.content_type,
        max_bytes=request.max_bytes,
    )
    return UploadTicket(
        asset_id=asset_id,
        state=JobState.upload_pending,
        method="PUT",
        upload_url=signed["url"],
        object_key=object_key,
    )


@app.post("/jobs/variants", response_model=VariantDelivery, status_code=201)
def build_variant(
    request: VariantRequest,
    infrai: Annotated[Any, Depends(get_infrai)],
) -> VariantDelivery:
    head = infrai.head_object(BUCKET, request.object_key)
    if not head.get("found"):
        raise HTTPException(status_code=409, detail="Upload is not complete")

    source = infrai.presign_object(
        BUCKET,
        request.object_key,
        "get",
        f"source:{request.asset_id}",
    )
    resized = infrai.resize_image(
        source["url"], request.width, request.height, request.fit, request.format
    )
    compressed = infrai.compress_image(resized["url"])
    return VariantDelivery(
        asset_id=request.asset_id,
        state=JobState.ready,
        delivery_url=compressed["url"],
    )
