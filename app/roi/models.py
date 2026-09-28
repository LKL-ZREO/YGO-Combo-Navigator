from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.capture.models import PixelRect


@dataclass(slots=True)
class NormalizedROI:
    name: str
    label: str
    x: float
    y: float
    width: float
    height: float
    color: tuple[int, int, int] = (0, 255, 0)

    def validate(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(value < 0 or value > 1 for value in values):
            raise ValueError(f"ROI values must be between 0 and 1: {self.name}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"ROI must have positive dimensions: {self.name}")
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError(f"ROI extends beyond the frame: {self.name}")
        if len(self.color) != 3 or any(channel < 0 or channel > 255 for channel in self.color):
            raise ValueError(f"ROI color must be an RGB triplet: {self.name}")

    def resolve(self, frame_width: int, frame_height: int) -> PixelRect:
        self.validate()
        return PixelRect(
            left=round(self.x * frame_width),
            top=round(self.y * frame_height),
            width=max(1, round(self.width * frame_width)),
            height=max(1, round(self.height * frame_height)),
        )


@dataclass(slots=True)
class ROIProfile:
    profile_id: str
    game: str
    language: str
    reference_width: int
    reference_height: int
    regions: list[NormalizedROI]

    @classmethod
    def load(cls, path: Path) -> "ROIProfile":
        payload = json.loads(path.read_text(encoding="utf-8"))
        regions = []
        for region_payload in payload["regions"]:
            region_payload = dict(region_payload)
            region_payload["color"] = tuple(region_payload.get("color", (0, 255, 0)))
            region = NormalizedROI(**region_payload)
            region.validate()
            regions.append(region)
        profile = cls(
            profile_id=payload["profile_id"],
            game=payload["game"],
            language=payload["language"],
            reference_width=int(payload["reference_width"]),
            reference_height=int(payload["reference_height"]),
            regions=regions,
        )
        profile.validate()
        return profile

    def save(self, path: Path) -> None:
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profile_id": self.profile_id,
            "game": self.game,
            "language": self.language,
            "reference_width": self.reference_width,
            "reference_height": self.reference_height,
            "regions": [],
        }
        for region in self.regions:
            region_payload = asdict(region)
            region_payload["color"] = list(region.color)
            payload["regions"].append(region_payload)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def validate(self) -> None:
        if self.reference_width <= 0 or self.reference_height <= 0:
            raise ValueError("Reference dimensions must be positive")
        names: set[str] = set()
        for region in self.regions:
            region.validate()
            if region.name in names:
                raise ValueError(f"Duplicate ROI name: {region.name}")
            names.add(region.name)

    def get_region(self, name: str) -> NormalizedROI:
        for region in self.regions:
            if region.name == name:
                return region
        raise KeyError(name)

