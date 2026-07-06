"""
Nutrient lookup + meal analysis.

Rewritten from the original prototype to:
- load the CSV once and build an O(1) name index instead of re-scanning /
  re-reading the dataframe on every request (the old `/food_search` route
  re-read the CSV from disk on every keystroke)
- normalize column names defensively so a renamed/reordered CSV doesn't
  silently produce all-zero nutrition
- do real fuzzy matching (difflib) with a confidence score surfaced to the
  caller instead of failing silently to zeros
- never call fillna on a column that may not exist (the old code assumed
  all five nutrient columns were always present)
"""
from __future__ import annotations

import difflib
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical nutrient keys -> the possible CSV header spellings we accept.
COLUMN_ALIASES = {
    "calories": ["Calories (kcal)", "Calories", "calories"],
    "carbs": ["Carbohydrates (g)", "Carbs (g)", "carbohydrates", "carbs"],
    "protein": ["Protein (g)", "protein"],
    "fat": ["Fats (g)", "Fat (g)", "fats", "fat"],
    "sugar": ["Free Sugar (g)", "sugar"],
    "fibre": ["Fibre (g)", "Fiber (g)", "fibre", "fiber"],
    "sodium": ["Sodium (mg)", "sodium"],
    "calcium": ["Calcium (mg)", "calcium"],
    "iron": ["Iron (mg)", "iron"],
    "vitamin_c": ["Vitamin C (mg)", "vitamin c"],
    "folate": ["Folate (µg)", "Folate (mcg)", "folate"],
}

NAME_COLUMN_ALIASES = ["Dish Name", "dish name", "food", "name"]

# Suggestion thresholds are centralized so they're easy to tune / unit test.
LOW_PROTEIN_G = 50
LOW_CARBS_G = 200
LOW_FAT_G = 60
LOW_CALORIES_KCAL = 1800
HIGH_PROTEIN_G = 120
HIGH_FAT_G = 100


@dataclass
class FoodRecord:
    name: str
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0
    extra: dict = field(default_factory=dict)

    def as_dict(self):
        return {
            "name": self.name,
            "calories": round(self.calories, 1),
            "protein": round(self.protein, 1),
            "carbs": round(self.carbs, 1),
            "fat": round(self.fat, 1),
        }


class FoodDatabase:
    """Thread-safe, lazily-loaded nutrition database backed by a CSV file."""

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._lock = threading.Lock()
        self._df: Optional[pd.DataFrame] = None
        self._index: dict[str, int] = {}
        self._names_lower: list[str] = []
        self.load_error: Optional[str] = None

    # ---------- loading ----------
    def _resolve_column(self, df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
        lower_map = {c.strip().lower(): c for c in df.columns}
        for alias in aliases:
            hit = lower_map.get(alias.strip().lower())
            if hit:
                return hit
        return None

    def load(self, force: bool = False) -> None:
        with self._lock:
            if self._df is not None and not force:
                return
            try:
                df = pd.read_csv(self.csv_path)
            except Exception as exc:  # missing file, bad encoding, etc.
                logger.error("Could not load food database from %s: %s", self.csv_path, exc)
                self.load_error = str(exc)
                self._df = pd.DataFrame()
                return

            df.columns = [c.strip() for c in df.columns]
            name_col = self._resolve_column(df, NAME_COLUMN_ALIASES)
            if name_col is None:
                self.load_error = "CSV has no recognizable dish-name column."
                self._df = pd.DataFrame()
                return

            df = df.rename(columns={name_col: "_name"})
            df["_name"] = df["_name"].astype(str).str.strip()
            df["_name_lower"] = df["_name"].str.lower()

            resolved = {}
            for key, aliases in COLUMN_ALIASES.items():
                col = self._resolve_column(df, aliases)
                if col:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
                    resolved[key] = col
                else:
                    df[key] = 0.0
                    resolved[key] = key

            self._resolved_columns = resolved
            df = df.drop_duplicates(subset="_name_lower", keep="first").reset_index(drop=True)

            self._df = df
            self._names_lower = df["_name_lower"].tolist()
            self._index = {name: i for i, name in enumerate(self._names_lower)}
            self.load_error = None
            logger.info("Loaded %d food records from %s", len(df), self.csv_path)

    @property
    def is_ready(self) -> bool:
        self.load()
        return self._df is not None and not self._df.empty

    def all_names(self) -> list[str]:
        self.load()
        if self._df is None or self._df.empty:
            return []
        return sorted(self._df["_name"].unique().tolist())

    def _row_to_record(self, row) -> FoodRecord:
        cols = self._resolved_columns
        return FoodRecord(
            name=row["_name"],
            calories=float(row[cols["calories"]]),
            protein=float(row[cols["protein"]]),
            carbs=float(row[cols["carbs"]]),
            fat=float(row[cols["fat"]]),
            extra={
                "sugar": float(row[cols["sugar"]]),
                "fibre": float(row[cols["fibre"]]),
                "sodium": float(row[cols["sodium"]]),
                "calcium": float(row[cols["calcium"]]),
                "iron": float(row[cols["iron"]]),
                "vitamin_c": float(row[cols["vitamin_c"]]),
                "folate": float(row[cols["folate"]]),
            },
        )

    def exact_lookup(self, name: str) -> Optional[FoodRecord]:
        self.load()
        if not name or self._df is None or self._df.empty:
            return None
        idx = self._index.get(name.strip().lower())
        if idx is None:
            return None
        return self._row_to_record(self._df.iloc[idx])

    def fuzzy_lookup(self, name: str, cutoff: float = 0.6) -> tuple[Optional[FoodRecord], float]:
        """Returns (record_or_None, confidence 0..1).

        Tries, in order: exact match -> prefix match -> substring containment
        -> difflib ratio. The containment checks come before pure fuzzy
        ratio because dataset entries like "Hot tea (Garam Chai)" would
        otherwise lose to an unrelated but character-similar name such as
        "Hot cocoa" when scored purely on edit distance.
        """
        self.load()
        if not name or self._df is None or self._df.empty:
            return None, 0.0

        cleaned = name.strip().lower()
        exact = self.exact_lookup(cleaned)
        if exact:
            return exact, 1.0

        starts_with = [n for n in self._names_lower if n.startswith(cleaned)]
        if starts_with:
            best = min(starts_with, key=len)
            idx = self._index[best]
            return self._row_to_record(self._df.iloc[idx]), 0.95

        contains = [n for n in self._names_lower if cleaned in n]
        if contains:
            best = min(contains, key=len)
            idx = self._index[best]
            return self._row_to_record(self._df.iloc[idx]), 0.85

        candidates = difflib.get_close_matches(cleaned, self._names_lower, n=5, cutoff=cutoff)
        if not candidates:
            return None, 0.0

        best_name = max(candidates, key=lambda c: difflib.SequenceMatcher(None, cleaned, c).ratio())
        ratio = difflib.SequenceMatcher(None, cleaned, best_name).ratio()
        idx = self._index[best_name]
        return self._row_to_record(self._df.iloc[idx]), round(ratio, 2)

    def search(self, query: str, limit: int = 10) -> list[FoodRecord]:
        self.load()
        if self._df is None or self._df.empty or not query:
            return []
        q = query.strip().lower()
        mask = self._df["_name_lower"].str.contains(q, na=False, regex=False)
        rows = self._df[mask].head(limit)
        return [self._row_to_record(r) for _, r in rows.iterrows()]


def build_nutrition_suggestions(totals: dict) -> list[str]:
    suggestions = []
    if totals.get("protein", 0) < LOW_PROTEIN_G:
        suggestions.append("Add high-protein foods like paneer, lentils (dal), or eggs.")
    if totals.get("carbs", 0) < LOW_CARBS_G:
        suggestions.append("Include complex carbs such as rice, oats, or whole grains.")
    if totals.get("fat", 0) < LOW_FAT_G:
        suggestions.append("Add healthy fats such as nuts, seeds, or ghee.")
    if totals.get("calories", 0) < LOW_CALORIES_KCAL:
        suggestions.append("Your total calories are on the low side — consider a smoothie or snack.")
    if totals.get("protein", 0) > HIGH_PROTEIN_G:
        suggestions.append("Protein is quite high — balance the plate with more vegetables or carbs.")
    if totals.get("fat", 0) > HIGH_FAT_G:
        suggestions.append("Fat intake is high — consider cutting back on fried foods today.")
    return suggestions


_db_instances: dict[str, FoodDatabase] = {}


def get_food_db(csv_path: str) -> FoodDatabase:
    """Process-wide singleton per CSV path, so the file is parsed once
    instead of once-per-request (the original prototype re-read the CSV
    inside the /food_search endpoint on every single call)."""
    if csv_path not in _db_instances:
        _db_instances[csv_path] = FoodDatabase(csv_path)
    return _db_instances[csv_path]


class NutrientAnalyzer:

    """High-level analysis operations used by the meal-logging and
    meal-analyzer routes. Wraps a FoodDatabase instance."""

    def __init__(self, db: FoodDatabase):
        self.db = db

    def analyze_items(self, item_names: list[str]) -> dict:
        if not self.db.is_ready:
            return {"error": self.db.load_error or "Food database is unavailable right now."}

        analyzed = []
        unmatched = []
        totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

        for raw_name in item_names:
            name = (raw_name or "").strip()
            if not name:
                continue
            record, confidence = self.db.fuzzy_lookup(name)
            if record is None:
                unmatched.append(name)
                continue
            entry = record.as_dict()
            entry["query"] = name
            entry["match_confidence"] = confidence
            analyzed.append(entry)
            totals["calories"] += record.calories
            totals["protein"] += record.protein
            totals["carbs"] += record.carbs
            totals["fat"] += record.fat

        totals = {k: round(v, 1) for k, v in totals.items()}
        result = {
            "foods": analyzed,
            "totals": totals,
            "suggestions": build_nutrition_suggestions(totals),
        }
        if unmatched:
            result["unmatched"] = unmatched
        return result

    def analyze_free_text(self, text: str) -> dict:
        """Splits a free-text meal description on commas/'and' and analyzes
        each fragment. This is intentionally simple (no NLP dependency) but
        robust: empty/garbage fragments are dropped instead of crashing."""
        if not text or not text.strip():
            return {"error": "Please describe at least one item you ate."}

        normalized = text.replace(" and ", ",")
        items = [x.strip() for x in normalized.split(",") if x.strip()]
        if not items:
            return {"error": "Please describe at least one item you ate."}

        result = self.analyze_items(items)
        if "error" in result:
            return result

        result["parsed_items"] = result["foods"]
        return result
