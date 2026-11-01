from fastapi import UploadFile

from app.core.errors import AppError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
_PNG = b"\x89PNG\r\n\x1a\n"


def image_media_type(head: bytes) -> str | None:
    """파일 첫 바이트(시그니처)로 jpeg·png·webp를 가린다. 보낸 Content-Type은 믿지 않는다."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(_PNG):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _invalid(message: str) -> AppError:
    # 보낸 값은 메시지에 넣지 않는다
    error = {"loc": ["body", "image"], "msg": message, "type": "value_error"}
    return AppError("VALIDATION_ERROR", 422, message, {"errors": [error]})


def read_image(upload: UploadFile) -> tuple[bytes, str]:
    """업로드를 읽고 (바이트, media_type)을 돌려준다. 크기·형식 위반은 422."""
    data = upload.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise _invalid("이미지는 5MB 이하여야 합니다")
    media_type = image_media_type(data)
    if media_type is None:
        raise _invalid("이미지 파일(jpeg·png·webp)이 필요합니다")
    return data, media_type
