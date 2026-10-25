from __future__ import annotations

import asyncio
import json
from functools import cache
from typing import TYPE_CHECKING

import boto3
from agents import TResponseInputItem
from botocore.config import Config

from moobot.settings import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

settings = get_settings()


@cache
def get_client() -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=Config(s3={"addressing_style": "path"}),
    )


def _get_transcript(key: str) -> list[TResponseInputItem]:
    client = get_client()
    try:
        response = client.get_object(Bucket=settings.s3_bucket, Key=key)
    except client.exceptions.NoSuchKey:
        return []
    items: list[TResponseInputItem] = json.loads(response["Body"].read())
    return items


def _set_transcript(key: str, items: list[TResponseInputItem]) -> None:
    get_client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=json.dumps(items).encode(),
        ContentType="application/json",
    )


async def get_transcript(key: str) -> list[TResponseInputItem]:
    return await asyncio.to_thread(_get_transcript, key)


async def set_transcript(key: str, items: list[TResponseInputItem]) -> None:
    await asyncio.to_thread(_set_transcript, key, items)
