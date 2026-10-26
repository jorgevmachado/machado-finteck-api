from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.domain.receipt.file import file as receipt_file


def upload(content=b"receipt", filename="receipt.pdf", content_type="application/pdf"):
    headers = {} if content_type is None else {"content-type": content_type}
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers(headers),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["application/pdf", "image/jpeg", "image/png"])
async def test_validate_file_returns_content_for_allowed_types(content_type):
    content = b"receipt content"
    assert (
        await receipt_file.validate_file(upload(content, content_type=content_type))
        == content
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", [None, ""])
async def test_validate_file_rejects_missing_filename_before_reading(filename):
    file = upload(filename=filename)
    with pytest.raises(HTTPException) as caught:
        await receipt_file.validate_file(file)
    assert caught.value.status_code == 400
    assert caught.value.detail == "File name is required."
    assert file.file.tell() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/octet-stream", None]
)
async def test_validate_file_rejects_unsupported_types_before_reading(content_type):
    file = upload(content_type=content_type)
    with pytest.raises(HTTPException) as caught:
        await receipt_file.validate_file(file)
    assert caught.value.status_code == 422
    assert (
        caught.value.detail
        == "Unsupported file type. Allowed types are: PDF, JPEG, PNG."
    )
    assert file.file.tell() == 0


@pytest.mark.asyncio
async def test_validate_file_rejects_empty_content():
    with pytest.raises(HTTPException) as caught:
        await receipt_file.validate_file(upload(b""))
    assert caught.value.status_code == 422
    assert caught.value.detail == "File is empty."


@pytest.mark.asyncio
async def test_validate_file_accepts_exact_size_limit_and_rejects_one_byte_over(
    monkeypatch,
):
    monkeypatch.setattr(receipt_file, "MAX_FILE_SIZE", 4)
    assert await receipt_file.validate_file(upload(b"1234")) == b"1234"
    with pytest.raises(HTTPException) as caught:
        await receipt_file.validate_file(upload(b"12345"))
    assert caught.value.status_code == 422
    assert (
        caught.value.detail == "File size exceeds the maximum allowed size of 4 bytes."
    )


@pytest.mark.parametrize("count", [0, 2, 3])
def test_validate_batch_size_enforces_configured_limit(monkeypatch, count):
    monkeypatch.setattr(receipt_file, "MAX_BATCH_FILES", 2)
    files = [upload() for _ in range(count)]
    if count <= 2:
        receipt_file.validate_batch_size(files)
    else:
        with pytest.raises(HTTPException) as caught:
            receipt_file.validate_batch_size(files)
        assert caught.value.status_code == 400
        assert caught.value.detail == "A maximum of 2 files can be uploaded at once."


def test_calculate_hash_uses_sha256_of_file_content():
    assert receipt_file.calculate_hash(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
