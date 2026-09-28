from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


CATALOG_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
ZH_HANS_CARDSET_URL = "https://ygocdb.com/api/v0/cardset"
USER_AGENT = "YGOComboNavigator/0.1 (+local-development)"


@dataclass(frozen=True, slots=True)
class CardRecord:
    card_id: int
    name: str
    card_type: str
    frame_type: str
    image_url: str
    localized_name: str | None = None

    @property
    def display_name(self) -> str:
        return self.localized_name or self.name or str(self.card_id)


class CardNameLocalizer:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self._names: dict[int, str] = {}
        self._loaded = False
        self.last_sync_error: str | None = None

    def load(self) -> None:
        if not self.cache_path.exists():
            self._loaded = True
            return
        payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self._names = {
            int(card_id): str(name).strip()
            for card_id, name in payload.get("names", {}).items()
            if str(name).strip()
        }
        self._loaded = True

    def localize(
        self,
        records: list[CardRecord],
        *,
        sync_missing: bool = True,
    ) -> list[CardRecord]:
        if not self._loaded:
            self.load()
        missing = [record.card_id for record in records if record.card_id not in self._names]
        self.last_sync_error = None
        if missing and sync_missing:
            try:
                self.sync(tuple(missing))
            except (RuntimeError, ValueError) as exc:
                self.last_sync_error = str(exc)
        return [
            replace(record, localized_name=self._names.get(record.card_id))
            for record in records
        ]

    def sync(self, card_ids: tuple[int, ...], *, timeout: float = 30.0) -> None:
        requested_ids = tuple(dict.fromkeys(card_ids))
        if not requested_ids:
            return
        request = urllib.request.Request(
            ZH_HANS_CARDSET_URL,
            data=json.dumps({"ids": requested_ids}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unable to download Chinese card names: {exc}") from exc

        parsed = self._parse_cardset_names(payload, requested_ids)
        self._names.update(parsed)
        self._save()

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "locale": "zh-Hans",
            "source": ZH_HANS_CARDSET_URL,
            "names": {
                str(card_id): name for card_id, name in sorted(self._names.items())
            },
        }
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _parse_cardset_names(
        payload: dict,
        card_ids: tuple[int, ...],
    ) -> dict[int, str]:
        names: dict[int, str] = {}
        for card_id in card_ids:
            item = payload.get(str(card_id))
            if not isinstance(item, dict):
                continue
            text = item.get("text") or {}
            name = (
                text.get("md_name")
                or text.get("sc_name")
                or text.get("name")
                or item.get("md_name")
                or item.get("sc_name")
                or item.get("cn_name")
            )
            if name and str(name).strip():
                names[card_id] = str(name).strip()
        return names


class CardCatalog:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self._cards: dict[int, CardRecord] = {}

    @property
    def is_loaded(self) -> bool:
        return bool(self._cards)

    def load(self) -> None:
        payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self._cards = self._parse_records(payload)

    def sync(self, *, timeout: float = 60.0) -> None:
        request = urllib.request.Request(CATALOG_URL, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw_payload = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Unable to download the card catalog: {exc}") from exc

        payload = json.loads(raw_payload.decode("utf-8"))
        cards = self._parse_records(payload)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        self._cards = cards

    def ensure_loaded(self) -> None:
        if self.is_loaded:
            return
        if self.cache_path.exists():
            self.load()
        else:
            self.sync()

    def get(self, card_id: int) -> CardRecord:
        self.ensure_loaded()
        try:
            return self._cards[card_id]
        except KeyError as exc:
            raise KeyError(f"Card ID {card_id} was not found in the local catalog") from exc

    def get_many(self, card_ids: tuple[int, ...]) -> list[CardRecord]:
        return [self.get(card_id) for card_id in card_ids]

    @staticmethod
    def _parse_records(payload: dict) -> dict[int, CardRecord]:
        records: dict[int, CardRecord] = {}
        for item in payload.get("data", []):
            images = item.get("card_images") or []
            if not images:
                continue
            card_id = int(item["id"])
            image = images[0]
            image_url = image.get("image_url") or image.get("image_url_small")
            if not image_url:
                continue
            records[card_id] = CardRecord(
                card_id=card_id,
                name=str(item.get("name", card_id)),
                card_type=str(item.get("type", "Unknown")),
                frame_type=str(item.get("frameType", "unknown")),
                image_url=str(image_url),
            )
        if not records:
            raise ValueError("The card catalog contains no usable card records")
        return records


class ArtworkRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def image_path(self, card_id: int) -> Path:
        return self.root / f"{card_id}.jpg"

    def ensure_images(
        self,
        records: list[CardRecord],
        *,
        progress: Callable[[int, int, CardRecord], None] | None = None,
        timeout: float = 30.0,
    ) -> list[Path]:
        self.root.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        total = len(records)
        for index, record in enumerate(records, start=1):
            path = self.image_path(record.card_id)
            if not self._is_valid_image(path):
                self._download_image(record, path, timeout=timeout)
                time.sleep(0.06)
            paths.append(path)
            if progress:
                progress(index, total, record)
        return paths

    @staticmethod
    def _is_valid_image(path: Path) -> bool:
        if not path.exists() or path.stat().st_size < 1024:
            return False
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        return image is not None and image.shape[0] > 100 and image.shape[1] > 100

    @staticmethod
    def _download_image(record: CardRecord, path: Path, *, timeout: float) -> None:
        request = urllib.request.Request(record.image_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw_image = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Unable to download artwork for {record.display_name}: {exc}"
            ) from exc

        image = cv2.imdecode(np.frombuffer(raw_image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(
                f"Downloaded artwork is not a valid image: {record.display_name}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".download")
        temporary_path.write_bytes(raw_image)
        temporary_path.replace(path)

