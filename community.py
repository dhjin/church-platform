"""커뮤니티 게시판 도우미: 사진 정리, 글쓰기 횟수 제한.

사진은 서버에서 다시 그려 저장한다.
- 진짜 그림 파일인지 확인한다(확장자만 바꾼 파일은 거른다).
- 긴 변을 MAX_SIDE 로 줄여 용량을 아낀다.
- 휴대폰 사진의 위치(GPS)·기기 정보(EXIF)를 지운다. 방향은 먼저 바로잡는다.
"""
import io
import os
import secrets

from PIL import Image, ImageOps, UnidentifiedImageError

from signup_guard import RateLimiter

MAX_PHOTOS = 10
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_SIDE = 1600
MAX_TITLE = 120
MAX_CONTENT = 5000
PER_PAGE = 12
ALLOWED_FORMATS = {"JPEG", "PNG", "GIF", "WEBP", "MPO"}

# 30메가픽셀이 넘는 그림은 압축 폭탄일 수 있어 열지 않는다.
Image.MAX_IMAGE_PIXELS = 30_000_000

post_limiter = RateLimiter(limit=int(os.getenv("BOARD_POSTS_PER_HOUR", "10")), window=3600)


class PhotoError(ValueError):
    pass


def process_photo(data: bytes) -> tuple:
    """올린 사진을 검사하고 다시 저장한다. (bytes, 확장자) 를 돌려준다."""
    if not data:
        raise PhotoError("빈 파일입니다.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise PhotoError("사진 한 장은 15MB 까지 올릴 수 있습니다.")
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            raise PhotoError("jpg, png, gif, webp 사진만 올릴 수 있습니다.")
        img.draft("RGB", (MAX_SIDE, MAX_SIDE))  # 큰 JPEG 는 줄여서 읽어 메모리를 아낀다
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise PhotoError("사진 파일을 읽을 수 없습니다.")
    out = io.BytesIO()
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img.convert("RGBA").save(out, "PNG", optimize=True)
        return out.getvalue(), ".png"
    img.convert("RGB").save(out, "JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue(), ".jpg"


def photo_filename(ext: str) -> str:
    return f"board_{secrets.token_hex(8)}{ext}"
