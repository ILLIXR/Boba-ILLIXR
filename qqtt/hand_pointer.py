"""Phone-demo hand artwork adapted to the existing native line overlays."""

# Fingertip anchoring adapted from Boba-Phone-Demo's _load_demo2_hand_icons.
# Copyright (c) 2025 Hanxiao Jiang; MIT license in assets/hand_pointer/LICENSE.

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


@lru_cache(maxsize=2)
def hand_pointer_strokes(source):
    """Return cached colored scanlines, with the index fingertip at (0, 0).

    The native overlay already carries colored lines. Sampling the two flat-color
    icons once keeps that transport and its menu texture cache unchanged.
    Fingertip anchoring follows the phone demo's largest-component calculation.
    """
    filename = {"left": "Picture2.png", "right": "Picture1.png"}[source]
    path = Path(__file__).resolve().parents[1] / "assets" / "hand_pointer" / filename
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"))

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (rgba[:, :, 3] > 0).astype(np.uint8), connectivity=8)
    if component_count < 2:
        raise ValueError(f"Hand icon has no opaque component: {path}")
    hand_label = 1 + int(np.argmax(stats[1:, 4]))
    # The phone artwork also has detached arrows. Keep only the hand itself,
    # using the same connected component that identifies the fingertip.
    hand_alpha = np.where(labels == hand_label, rgba[:, :, 3], 0).astype(np.uint8)
    small_alpha = np.asarray(Image.fromarray(hand_alpha).resize(
        (48, 48), Image.Resampling.LANCZOS))
    hand_y, hand_x = np.where(labels == hand_label)
    fingertip_y = int(hand_y.min())
    fingertip_x = float(np.median(hand_x[hand_y <= fingertip_y + 3]))
    anchor_x = fingertip_x / (rgba.shape[1] - 1) * 47
    anchor_y = fingertip_y / (rgba.shape[0] - 1) * 47
    color = tuple(float(value) for value in np.median(rgba[labels == hand_label, :3], axis=0))

    strokes = []
    for y, row in enumerate(small_alpha >= 128):
        edges = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            strokes.append((float(start) - 0.5 - anchor_x, y - anchor_y,
                            float(end) - 0.5 - anchor_x, y - anchor_y))
    return color, tuple(strokes)
