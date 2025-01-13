from abc import ABC, abstractmethod

from pydantic import BaseModel
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from datetime import datetime
from pathlib import Path
from typing import Optional
import aiofiles
import hashlib

class ListingItem(BaseModel):
    Key: str
    LastModified: datetime
    ETag: str
    Size: int


async def calculate_file_md5(local_filepath: Path) -> str:
    hasher = hashlib.md5()
    async with aiofiles.open(local_filepath, 'rb') as f:
        while True:
            chunk = await f.read(8192)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


class FileService(ABC):

    @abstractmethod
    async def download_file(self, s3_path: str, file_path: Optional[Path] = None) -> tuple[str, str]:
        pass

    @abstractmethod
    async def upload_file(self, file_path: Path, s3_path: str) -> str:
        pass

    @abstractmethod
    async def upload_bytes(self, file_contents: bytes, s3_path: str) -> str:
        pass

    @abstractmethod
    async def get_modified_date(self, s3_path: str) -> datetime:
        pass

    @abstractmethod
    async def get_listing(self, s3_path: str) -> list[ListingItem]:
        pass

    @abstractmethod
    async def get_file_contents(self, s3_path: str) -> bytes:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass