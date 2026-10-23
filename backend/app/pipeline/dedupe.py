"""Duplicate-evidence index: exact (SHA-256) for files, perceptual hash for photographs.

PDF pages are compared only exactly: certificates from one issuer share a template, so perceptual
matching on them would mostly find the template. Photographs use a 64-bit DCT perceptual hash.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

PHASH_MAX_DISTANCE = 6


def phash_image(data: bytes) -> str:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    arr = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    digest = cv2.img_hash.pHash(arr)  # 8 bytes
    return bytes(digest.flatten().tolist()).hex()


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")
