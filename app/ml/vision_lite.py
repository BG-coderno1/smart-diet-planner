"""
Classical computer-vision fallback for food photo recognition.

This backend needs no GPU, no internet, and no pretrained weight download —
everything it needs is generated and trained in-process from a small,
hand-specified set of reference color/texture signatures per broad food
category. It is intentionally coarse: it recognizes *categories* of food
(rice/grain dish, roti or flatbread, lentil/gravy curry, leafy-green dish,
deep-fried snack, sweet/dessert, beverage) rather than exact dishes, then
narrows to specific dishes by matching those categories' typical keywords
against the nutrition database.

Use `vision_deep.py` (MobileNetV3 transfer learning) for real per-dish
recognition once torch/torchvision + a labeled food-image dataset are
available; this module is the dependency-free tier that keeps the feature
usable everywhere in the meantime, and the same `predict()` contract lets
the app swap backends without touching calling code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import cv2
from sklearn.neighbors import KNeighborsClassifier

logger = logging.getLogger(__name__)

# category -> (hue center 0-179, hue spread, saturation center 0-255, value center 0-255,
#              typical edge-density band, keywords used to narrow to real dishes)
CATEGORY_PROFILES = {
    "rice_or_grain": dict(hue=25, hue_spread=12, sat=60, val=200, edge=0.05,
                           keywords=["rice", "biryani", "pulao", "khichdi", "poha"]),
    "roti_or_flatbread": dict(hue=20, hue_spread=10, sat=90, val=170, edge=0.10,
                               keywords=["roti", "chapati", "naan", "paratha", "puri"]),
    "dal_or_gravy_curry": dict(hue=18, hue_spread=10, sat=160, val=150, edge=0.08,
                                keywords=["dal", "curry", "gravy", "masala", "sabzi", "sambar"]),
    "leafy_or_green_dish": dict(hue=55, hue_spread=15, sat=140, val=140, edge=0.09,
                                 keywords=["palak", "saag", "salad", "beans", "cabbage", "spinach"]),
    "fried_snack": dict(hue=22, hue_spread=8, sat=170, val=160, edge=0.22,
                         keywords=["fried", "pakora", "samosa", "vada", "chips", "bhaji"]),
    "sweet_or_dessert": dict(hue=15, hue_spread=20, sat=110, val=210, edge=0.06,
                              keywords=["sweet", "halwa", "kheer", "barfi", "laddu", "gulab", "payasam"]),
    "beverage": dict(hue=15, hue_spread=25, sat=90, val=190, edge=0.02,
                      keywords=["tea", "coffee", "juice", "lassi", "milk", "drink"]),
}

_RNG = np.random.default_rng(42)  # fixed seed -> deterministic, reproducible training


@dataclass
class CategoryPrediction:
    category: str
    confidence: float
    keywords: list


def _synthetic_training_set(samples_per_class: int = 60):
    X, y = [], []
    for label, profile in CATEGORY_PROFILES.items():
        for _ in range(samples_per_class):
            hue = np.clip(_RNG.normal(profile["hue"], profile["hue_spread"]), 0, 179)
            sat = np.clip(_RNG.normal(profile["sat"], 30), 0, 255)
            val = np.clip(_RNG.normal(profile["val"], 30), 0, 255)
            edge = np.clip(_RNG.normal(profile["edge"], 0.03), 0, 1)
            X.append([hue, sat, val, edge])
            y.append(label)
    return np.array(X), np.array(y)


class VisionLiteEngine:
    """Trains a tiny KNN classifier once at process start (milliseconds) and
    reuses it for every prediction."""

    def __init__(self):
        X, y = _synthetic_training_set()
        self.classifier = KNeighborsClassifier(n_neighbors=7, weights="distance")
        self.classifier.fit(X, y)

    @staticmethod
    def _extract_features(image_bgr: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 160)
        edge_density = float(np.count_nonzero(edges)) / edges.size

        return np.array([float(np.mean(h)), float(np.mean(s)), float(np.mean(v)), edge_density])

    def predict(self, image_path: str, top_k: int = 3) -> list[CategoryPrediction]:
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError("Could not read image file (unsupported or corrupted format).")

        # Downscale for speed/consistency; feature extraction is resolution-sensitive
        image = cv2.resize(image, (256, 256))
        features = self._extract_features(image).reshape(1, -1)

        probs = self.classifier.predict_proba(features)[0]
        classes = self.classifier.classes_
        order = np.argsort(probs)[::-1][:top_k]

        results = []
        for idx in order:
            label = classes[idx]
            results.append(CategoryPrediction(
                category=label,
                confidence=round(float(probs[idx]), 3),
                keywords=CATEGORY_PROFILES[label]["keywords"],
            ))
        return results


_engine: VisionLiteEngine | None = None


def get_engine() -> VisionLiteEngine:
    global _engine
    if _engine is None:
        _engine = VisionLiteEngine()
    return _engine
