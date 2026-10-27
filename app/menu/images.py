"""Dish photos: normalise an image and host it on Supabase Storage.

Every photo is centre-cropped to 4:3 and saved as a ~800px JPEG, so cards line up and
the menu stays light on a phone. They live in a public bucket (`dish-images`) at
`<restaurant-slug>/<dish-id>.jpg`; the dish row just keeps the public URL in `image_url`.
The same `store_image` is what owner uploads will use later.
"""
import hashlib
import io

from PIL import Image, ImageOps

from app import db

BUCKET = "dish-images"
WIDTH, HEIGHT = 800, 600


def prepare(raw: bytes) -> bytes:
    """Any common image format in, an 800x600 JPEG out (cropped, not stretched)."""
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    image = ImageOps.fit(image, (WIDTH, HEIGHT), method=Image.LANCZOS, centering=(0.5, 0.5))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out.getvalue()


def ensure_bucket() -> None:
    client = db.get_client()
    if BUCKET not in [b.name for b in client.storage.list_buckets()]:
        client.storage.create_bucket(BUCKET, options={"public": True})


def store_image(restaurant_slug: str, dish_id: str, jpeg: bytes) -> str:
    """Upload (replacing any earlier photo) and return the public URL. A content hash in the
    URL means a replaced photo is never served stale from a browser or CDN cache."""
    path = f"{restaurant_slug}/{dish_id}.jpg"
    bucket = db.get_client().storage.from_(BUCKET)
    bucket.upload(path, jpeg, {"content-type": "image/jpeg", "upsert": "true"})
    return f"{bucket.get_public_url(path).split('?')[0]}?v={hashlib.sha1(jpeg).hexdigest()[:8]}"
