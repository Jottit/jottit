import os
import threading
from io import BytesIO
from pathlib import Path

import boto3
from flask import current_app
from PIL import Image

BUCKET_NAME = os.environ.get("BUCKET_NAME")

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}

MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB


def file_size(file):
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    return size


def validate_image(file):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        return "File type not allowed"
    if file_size(file) > MAX_IMAGE_SIZE:
        return "File too large (max 2MB)"
    return None


def crop_square(file, format):
    img = Image.open(file)
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    buf = BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf


def upload_image(key, file, content_type):
    if BUCKET_NAME:
        return _upload_to_s3(BUCKET_NAME, key, file, content_type)

    dest = Path(current_app.instance_path) / "uploads" / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file.read())
    return f"/uploads/{key}"


def delete_image(key):
    if BUCKET_NAME:
        return _delete_from_s3(BUCKET_NAME, key)

    dest = Path(current_app.instance_path) / "uploads" / key
    if dest.exists():
        dest.unlink()


_client = None
_client_lock = threading.Lock()


def _s3_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = boto3.client(
                    "s3",
                    endpoint_url=os.environ.get("AWS_ENDPOINT_URL_S3"),
                    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                )
    return _client


def _upload_to_s3(bucket, key, file, content_type):
    _s3_client().upload_fileobj(
        file,
        bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    storage_url = os.environ.get(
        "STORAGE_URL", f"https://{bucket}.fly.storage.tigris.dev"
    )
    return f"{storage_url}/{key}"


def _delete_from_s3(bucket, key):
    _s3_client().delete_object(Bucket=bucket, Key=key)
