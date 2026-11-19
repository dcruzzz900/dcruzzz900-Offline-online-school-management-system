"""V107: one passport-photograph rule for students, staff, parents and every other profile.

Every uploaded photograph is normalised to the same 4:5 portrait frame (PASSPORT_W x PASSPORT_H, JPEG):
  * the picture is first turned upright from its EXIF orientation (phone photos) and transparency is flattened onto white;
  * proportions are NEVER changed (no stretching);
  * a photo that is already close to 4:5 is scaled to fill and trimmed by at most a few percent, anchored towards the TOP so a face
    is never the part that is lost;
  * any other shape (a landscape snapshot, a very tall picture) is not cropped at all: the WHOLE photograph is fitted inside the
    frame on a soft blurred backdrop made from the same picture.
Frames in the application then simply show the stored image, so every frame looks the same."""
import io
from PIL import Image, ImageFilter, ImageOps

PASSPORT_W, PASSPORT_H = 600, 750
NEAR_RATIO_TOLERANCE = 0.18          # within 18% of 4:5 -> fill-and-trim; otherwise fit whole photo
FACE_ANCHOR_Y = 0.18                 # when trimming, keep the top: 0 = top edge, 0.5 = centre


def _flatten(img):
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def fit_passport(data, width=PASSPORT_W, height=PASSPORT_H):
    """bytes (any common image format) -> JPEG bytes at exactly width x height."""
    img = Image.open(io.BytesIO(data))
    img.load()
    img = _flatten(ImageOps.exif_transpose(img))
    w, h = img.size
    if w < 1 or h < 1:
        raise ValueError("Image has no size.")
    target = width / height
    ratio = w / h
    if abs(ratio - target) / target <= NEAR_RATIO_TOLERANCE:
        scale = max(width / w, height / h)                                 # fill, then trim the small excess
        nw, nh = max(width, round(w * scale)), max(height, round(h * scale))
        big = img.resize((nw, nh), Image.LANCZOS)
        left = (nw - width) // 2
        top = int((nh - height) * FACE_ANCHOR_Y)
        out = big.crop((left, top, left + width, top + height))
    else:
        scale = min(width / w, height / h)                                 # whole photograph, nothing cropped
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        fg = img.resize((nw, nh), Image.LANCZOS)
        bscale = max(width / w, height / h)
        back = img.resize((max(width, round(w * bscale)), max(height, round(h * bscale))), Image.BILINEAR)
        bl, bt = (back.width - width) // 2, (back.height - height) // 2
        out = back.crop((bl, bt, bl + width, bt + height)).filter(ImageFilter.GaussianBlur(24))
        out = Image.blend(out, Image.new("RGB", out.size, (255, 255, 255)), 0.35)
        out.paste(fg, ((width - nw) // 2, (height - nh) // 2))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue()


def save_passport(file_storage, directory, base_name):
    """Normalise an uploaded werkzeug FileStorage and write it as <base_name>.jpg; returns the stored file name."""
    import os
    os.makedirs(directory, exist_ok=True)
    file_storage.stream.seek(0)
    data = fit_passport(file_storage.read())
    name = f"{base_name}.jpg"
    with open(os.path.join(directory, name), "wb") as fh:
        fh.write(data)
    return name


LOGO_MAX = 600   # longest side in px: sharp on print, light on a phone


def fit_logo(data):
    """bytes (PNG / JPG / GIF, any size or phone orientation) -> PNG bytes. Turned upright from EXIF, transparency kept, empty transparent
    margins trimmed (so the logo fills its frame instead of floating in it), proportions never changed, longest side limited to LOGO_MAX."""
    img = Image.open(io.BytesIO(data))
    img.load()
    img = ImageOps.exif_transpose(img).convert("RGBA")
    box = img.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if box:
        img = img.crop(box)
    w, h = img.size
    if w < 1 or h < 1:
        raise ValueError("Image has no size.")
    if max(w, h) > LOGO_MAX:
        k = LOGO_MAX / max(w, h)
        img = img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
