"""
Single entry point the Flask routes call for photo-based food recognition.
Chooses between the deep (torchvision) and lite (OpenCV/sklearn) backends
and always returns the same shape, so the rest of the app never needs to
know which one ran.
"""
from __future__ import annotations

import logging

from app.ml.nutrient_analyzer import FoodDatabase

logger = logging.getLogger(__name__)


def _match_dishes(db: FoodDatabase, keywords: list[str], limit: int = 5):
    seen = {}
    for kw in keywords:
        for record in db.search(kw, limit=limit):
            seen[record.name] = record
    return list(seen.values())[:limit]


def analyze_food_photo(image_path: str, db: FoodDatabase, backend_preference: str = "auto") -> dict:
    """
    Returns:
        {
          "backend_used": "deep" | "lite",
          "predictions": [
              {"label": str, "confidence": float, "matched_foods": [FoodRecord.as_dict(), ...]}
          ],
          "note": str (optional, e.g. explaining a fallback happened)
        }
    or {"error": "..."} on failure.
    """
    from app.ml import vision_deep, vision_lite

    use_deep = backend_preference in ("auto", "deep") and vision_deep.is_available()

    try:
        if use_deep:
            engine = vision_deep.get_engine()
            raw_predictions = engine.predict(image_path)
            predictions = []
            for p in raw_predictions:
                record, _ = db.fuzzy_lookup(p.label)
                predictions.append({
                    "label": p.label,
                    "confidence": p.confidence,
                    "matched_foods": [record.as_dict()] if record else [],
                })
            return {"backend_used": "deep", "predictions": predictions}

        # Lite fallback (or explicit choice)
        engine = vision_lite.get_engine()
        raw_predictions = engine.predict(image_path)
        predictions = []
        for p in raw_predictions:
            matched = _match_dishes(db, p.keywords)
            predictions.append({
                "label": p.category.replace("_", " "),
                "confidence": p.confidence,
                "matched_foods": [m.as_dict() for m in matched],
            })

        note = None
        if backend_preference in ("auto", "deep"):
            note = (
                "Using the lightweight offline recognizer (broad food category, not exact dish). "
                "Install torch/torchvision and run train_food_classifier.py for exact-dish recognition."
            )
        return {"backend_used": "lite", "predictions": predictions, "note": note}

    except ValueError as exc:  # bad/corrupt image
        return {"error": str(exc)}
    except Exception:
        logger.exception("Vision analysis failed")
        return {"error": "Could not analyze this photo. Please try a clearer image."}
