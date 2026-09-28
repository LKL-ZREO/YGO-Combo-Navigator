from __future__ import annotations

import argparse
from pathlib import Path

from app.deck_packs.loader import build_deck_pack, load_deck_pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a .ygopack archive")
    parser.add_argument("source", type=Path, help="Deck pack source directory")
    parser.add_argument("output", type=Path, nargs="?", help="Output .ygopack file")
    args = parser.parse_args()

    source = args.source.resolve()
    pack = load_deck_pack(source)
    output = args.output or (
        source.parent / f"{pack.manifest.deck_pack_id}-{pack.manifest.version}.ygopack"
    )
    built_path = build_deck_pack(source, output)
    print(f"Built {built_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
