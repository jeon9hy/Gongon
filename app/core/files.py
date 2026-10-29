"""올린 파일 보관(D-111).

지금은 서버 디스크 폴더이고, 배포 때 같은 모양의 다른 보관소로 바꾼다(어댑터).
파일 이름은 서버가 만든 키만 쓴다(올린 사람이 준 이름을 경로에 쓰지 않는다).
그림 종류는 확장자가 아니라 파일 앞부분(매직 바이트)으로 확인한다.
"""

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings

# (앞부분, 종류, 확장자). WebP는 RIFF....WEBP라 따로 본다
_IMAGE_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
)


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """(종류, 확장자). 그림이 아니면 None."""
    for head, kind, ext in _IMAGE_SIGNATURES:
        if data.startswith(head):
            return kind, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


class LocalFileStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, folder: str, ext: str, data: bytes) -> str:
        """새 키로 저장하고 키("folder/임의이름.ext")를 돌려준다."""
        key = f"{folder}/{secrets.token_hex(16)}.{ext}"
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def path(self, key: str) -> Path:
        resolved = (self.root / key).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError("보관 폴더 밖의 키")
        return resolved


def get_file_store(settings: Annotated[Settings, Depends(get_settings)]) -> LocalFileStore:
    return LocalFileStore(settings.upload_dir)


FileStoreDep = Annotated[LocalFileStore, Depends(get_file_store)]
