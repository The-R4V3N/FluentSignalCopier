# Minimal imghdr shim for Python 3.13+
# Supports the common formats Telethon may touch.

# Licensed under the Attribution-NonCommercial-ShareAlike 4.0 International
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

def what(file, h=None):
    if h is None:
        with open(file, "rb") as f:
            h = f.read(64)

    # JPEG
    if h.startswith(b"\xff\xd8"):
        return "jpeg"

    # PNG
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    # GIF
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"

    # BMP
    if h[:2] == b"BM":
        return "bmp"

    # WEBP: RIFF....WEBP
    if len(h) >= 12 and h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "webp"

    # ICO
    if h[:4] == b"\x00\x00\x01\x00":
        return "ico"

    return None
