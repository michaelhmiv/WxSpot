import asyncio
from pathlib import Path
from typing import Protocol

import boto3
from botocore.config import Config

from wxspot.config import settings


class ObjectStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...


class LocalStorage:
    """Persistent compose volume for development only."""

    def __init__(self, root: Path):
        self.root = root

    async def put(self, key, data, content_type):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key):
        return await asyncio.to_thread((self.root / key).read_bytes)


class S3Storage:
    def __init__(self):
        s = settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            config=Config(
                s3={"addressing_style": s.s3_addressing_style},
                connect_timeout=10,
                read_timeout=20,
                retries={"max_attempts": 2},
            ),
        )

    async def put(self, key, data, content_type):
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key):
        def read():
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            with response["Body"] as stream:
                return stream.read()

        return await asyncio.to_thread(read)


def storage() -> ObjectStorage:
    return S3Storage() if settings().s3_bucket else LocalStorage(settings().media_dir)
