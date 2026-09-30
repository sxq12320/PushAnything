"""Import pictures once, keep originals, and create portable display copies."""
import hashlib
import io
import os
import shutil
from PIL import Image, ImageOps

import storage

MAX_BYTES = 40 * 1024 * 1024
MAX_EDGE = 2560


def import_bytes(raw, base_dir):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("图片需小于 40 MB")
    with Image.open(io.BytesIO(raw)) as image:
        fmt = image.format
        if fmt not in {"JPEG", "PNG", "WEBP", "GIF", "BMP"}:
            raise ValueError("支持 JPG、PNG、WebP、GIF 和 BMP 图片")
        if image.width * image.height > 60_000_000:
            raise ValueError("图片像素过大，请先缩小到 6000 万像素以内")
        digest = hashlib.sha256(raw).hexdigest()[:20]
        original_ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp"}[fmt]
        animated = bool(getattr(image, "is_animated", False))
        if animated:
            output, ext, size = raw, original_ext, image.size
        else:
            normalized = ImageOps.exif_transpose(image)
            normalized.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
            transparent = "A" in normalized.getbands() or "transparency" in normalized.info
            output_buffer = io.BytesIO()
            if transparent:
                ext = "png"
                normalized.convert("RGBA").save(output_buffer, "PNG", optimize=True)
            else:
                ext = "jpg"
                normalized.convert("RGB").save(output_buffer, "JPEG", quality=90, optimize=True,
                                                 icc_profile=normalized.info.get("icc_profile"))
            output, size = output_buffer.getvalue(), normalized.size
    assets = os.path.join(base_dir, "assets")
    original_dir = os.path.join(assets, "originals")
    with storage.lock:
        os.makedirs(original_dir, exist_ok=True)
        original = os.path.join(original_dir, f"{digest}.{original_ext}")
        path = os.path.join(assets, f"image_{digest}.{ext}")
        for target, data in ((original, raw), (path, output)):
            if not os.path.exists(target):
                with open(target, "xb") as handle:
                    handle.write(data)
    return {"ok": True, "src": "assets/" + os.path.basename(path),
            "path": path, "original_path": original, "width": size[0], "height": size[1],
            "bytes": len(output), "original_bytes": len(raw), "animated": animated}


def import_file(path, base_dir):
    if not os.path.isfile(path):
        raise ValueError("图片文件不存在")
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("图片需小于 40 MB")
    with open(path, "rb") as handle:
        return import_bytes(handle.read(), base_dir)


def relocate_markdown(md, old_dir, new_dir):
    """Copy referenced local assets while moving a draft; never touch source files."""
    import re
    import mdconvert
    if os.path.normcase(old_dir) == os.path.normcase(new_dir):
        return md

    def copy_src(src):
        src = src.strip().strip("<>")
        if mdconvert.is_remote(src) or src.startswith("data:"):
            return src
        path = mdconvert.local_path_of(src, old_dir)
        if not os.path.isfile(path):
            return src
        with open(path, "rb") as handle:
            raw = handle.read()
        imported = import_bytes(raw, new_dir)
        # Keep the original imported camera file as well as the display copy.
        originals = os.path.join(old_dir, "assets", "originals")
        name = os.path.basename(path)
        match = re.match(r"image_([a-f0-9]{20})\.", name)
        if match and os.path.isdir(originals):
            for filename in os.listdir(originals):
                if filename.startswith(match.group(1) + "."):
                    destination = os.path.join(new_dir, "assets", "originals", filename)
                    if not os.path.exists(destination):
                        shutil.copy2(os.path.join(originals, filename), destination)
        return imported["src"]

    md = re.sub(r'(!\[[^\]]*\]\()(<[^>]+>|[^)\s]+)([^)]*\))',
                lambda match: match[1] + copy_src(match[2]) + match[3], md)
    return re.sub(r'(<img\b[^>]*\bsrc=")([^"]+)(")',
                  lambda match: match[1] + copy_src(match[2]) + match[3], md, flags=re.I)
