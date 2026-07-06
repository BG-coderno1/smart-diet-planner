"""
Deep-learning food recognition backend (transfer learning on MobileNetV3-Small).

This is the "real" production CV path: a pretrained ImageNet backbone with a
replaced classification head, ready to be fine-tuned on a labeled food-photo
dataset (see `train_food_classifier.py` at the project root for the training
script and expected folder layout).

This module is imported lazily and guarded: if torch/torchvision aren't
installed, or no fine-tuned checkpoint exists yet, `is_available()` returns
False and the app automatically falls back to `vision_lite.py`. That keeps
the app fully functional out of the box while giving you a clear, correct
upgrade path to real per-dish recognition:

    pip install torch torchvision
    python train_food_classifier.py --data-dir data/food_images --epochs 15
    # writes model_weights/food_classifier.pt, picked up automatically

Nothing else in the codebase needs to change when you do this — `vision.py`
talks to both backends through the same `predict(image_path)` contract.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "model_weights")
CHECKPOINT_PATH = os.path.join(MODEL_DIR, "food_classifier.pt")
LABELS_PATH = os.path.join(MODEL_DIR, "labels.json")

IMAGE_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


@dataclass
class DishPrediction:
    label: str
    confidence: float


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401
        return True
    except ImportError:
        return False


def is_available() -> bool:
    """True only if torch/torchvision are installed AND a fine-tuned
    checkpoint has been trained. Both are required for real per-dish
    predictions; without a checkpoint we'd just be classifying into 1000
    generic ImageNet classes, which isn't useful for Indian dish lookup."""
    return _torch_available() and os.path.exists(CHECKPOINT_PATH) and os.path.exists(LABELS_PATH)


def build_model(num_classes: int):
    """Builds a MobileNetV3-Small with a fresh classification head sized to
    the number of dish classes. Kept as a standalone function so the exact
    same architecture is used at train time and inference time."""
    import torch.nn as nn
    from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights

    weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1
    model = mobilenet_v3_small(weights=weights)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model, weights.transforms()


class VisionDeepEngine:
    def __init__(self):
        if not is_available():
            raise RuntimeError(
                "Deep vision backend requested but torch/torchvision or a "
                "trained checkpoint is missing. Run train_food_classifier.py "
                "first, or use the lite backend."
            )
        import torch

        with open(LABELS_PATH) as f:
            self.labels = json.load(f)

        self.model, self.transforms = build_model(num_classes=len(self.labels))
        state_dict = torch.load(CHECKPOINT_PATH, map_location="cpu")
        self.model.load_state_dict(state_dict)
        self.model.eval()
        self._torch = torch

    def predict(self, image_path: str, top_k: int = 3) -> list[DishPrediction]:
        from PIL import Image

        torch = self._torch
        image = Image.open(image_path).convert("RGB")
        tensor = self.transforms(image).unsqueeze(0)

        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1)[0]

        top_probs, top_idx = torch.topk(probs, k=min(top_k, len(self.labels)))
        return [
            DishPrediction(label=self.labels[i], confidence=round(float(p), 3))
            for p, i in zip(top_probs.tolist(), top_idx.tolist())
        ]


_engine: "VisionDeepEngine | None" = None


def get_engine() -> VisionDeepEngine:
    global _engine
    if _engine is None:
        _engine = VisionDeepEngine()
    return _engine
