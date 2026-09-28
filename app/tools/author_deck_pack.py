from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from datetime import date
from pathlib import Path

from app.authoring.card_resolver import CardNameResolver
from app.authoring.generation import generate_validated_draft, validate_generated_payload
from app.authoring.prompting import (
    build_authoring_prompt,
    build_deck_inventory,
    load_combo_draft_schema,
)
from app.authoring.providers import OpenAIResponsesProvider, parse_json_response
from app.authoring.source_loader import (
    GuideSource,
    load_guide_file,
    load_guide_text,
    load_guide_url,
)
from app.cards.catalog import CardCatalog, CardNameLocalizer
from app.decks.ydk import load_ydk
from app.tools.create_deck_pack import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_NAMES_PATH,
    create_deck_pack_from_draft,
)


def _default_pack_id(ydk_path: Path) -> str:
    normalized = unicodedata.normalize("NFKD", ydk_path.stem).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    if slug:
        return slug
    digest = hashlib.sha256(ydk_path.read_bytes()).hexdigest()[:8]
    return f"deck-{digest}"


def _load_guide(args: argparse.Namespace) -> GuideSource:
    if args.guide_file is not None:
        return load_guide_file(args.guide_file)
    if args.guide_url is not None:
        return load_guide_url(args.guide_url)
    return load_guide_text(args.guide_text)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn a YDK and a combo guide into a validated .ygopack using AI"
    )
    parser.add_argument("--ydk", required=True, type=Path)
    guide_group = parser.add_mutually_exclusive_group(required=True)
    guide_group.add_argument("--guide-file", type=Path, help="UTF-8 text, Markdown, or HTML guide")
    guide_group.add_argument("--guide-url", help="Public HTTP(S) guide page")
    guide_group.add_argument("--guide-text", help="Guide text supplied directly on the command line")
    parser.add_argument("--deck-pack-id")
    parser.add_argument("--name")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--ruleset", default=f"MD_{date.today():%Y_%m_%d}")
    parser.add_argument("--author", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--draft-output", type=Path)
    parser.add_argument("--prompt-output", type=Path)
    parser.add_argument("--prompt-only", action="store_true")
    parser.add_argument("--response-file", type=Path, help="JSON returned by any external AI")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5-mini"))
    parser.add_argument("--api-base", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--names", type=Path, default=DEFAULT_NAMES_PATH)
    args = parser.parse_args()

    try:
        ydk_path = args.ydk.resolve()
        if not ydk_path.is_file():
            raise ValueError(f"YDK file does not exist: {ydk_path}")
        if args.prompt_only and args.prompt_output is None:
            raise ValueError("--prompt-only requires --prompt-output")

        deck = load_ydk(ydk_path)
        catalog = CardCatalog(args.catalog.resolve())
        catalog.ensure_loaded()
        localizer = CardNameLocalizer(args.names.resolve())
        resolver = CardNameResolver(deck, catalog, localizer)
        inventory = build_deck_inventory(deck, catalog, localizer)
        guide = _load_guide(args)
        schema = load_combo_draft_schema()
        deck_pack_id = args.deck_pack_id or _default_pack_id(ydk_path)
        pack_name = args.name or ydk_path.stem
        expected_metadata = {
            "deck_pack_id": deck_pack_id,
            "name": pack_name,
            "version": args.version,
            "ruleset": args.ruleset,
            "verification_status": "DRAFT",
            "author": args.author,
            "language": "zh-Hans",
            "sources": (guide.label,),
        }
        prompt = build_authoring_prompt(
            deck_inventory=inventory,
            guide=guide,
            deck_pack_id=deck_pack_id,
            name=pack_name,
            version=args.version,
            ruleset=args.ruleset,
            author=args.author,
            schema=schema,
        )
        if args.prompt_output is not None:
            prompt_output = args.prompt_output.resolve()
            prompt_output.parent.mkdir(parents=True, exist_ok=True)
            prompt_output.write_text(prompt, encoding="utf-8")
            print(f"Wrote AI prompt to {prompt_output}")
        if args.prompt_only:
            return 0

        attempts = 1
        if args.response_file is not None:
            payload = parse_json_response(args.response_file.read_text(encoding="utf-8-sig"))
            draft = validate_generated_payload(
                payload,
                deck,
                resolver,
                expected_metadata=expected_metadata,
            )
        else:
            api_key = os.environ.get(args.api_key_env, "")
            if not api_key:
                raise ValueError(
                    f"Environment variable {args.api_key_env} is empty. "
                    "Set it, use --response-file, or use --prompt-only."
                )
            generated = generate_validated_draft(
                OpenAIResponsesProvider(
                    api_key=api_key,
                    model=args.model,
                    base_url=args.api_base,
                ),
                prompt=prompt,
                schema=schema,
                deck=deck,
                resolver=resolver,
                max_attempts=args.max_attempts,
                expected_metadata=expected_metadata,
            )
            payload = generated.payload
            draft = generated.draft
            attempts = generated.attempts

        output = (args.output or Path(f"{deck_pack_id}-{args.version}.ygopack")).resolve()
        draft_output = (args.draft_output or output.with_suffix(".draft.json")).resolve()
        draft_output.parent.mkdir(parents=True, exist_ok=True)
        draft_output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        built = create_deck_pack_from_draft(
            ydk_path,
            draft,
            output,
            catalog_path=args.catalog,
            names_path=args.names,
        )
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(f"Built {built}")
    print(f"Saved validated draft to {draft_output}")
    print(f"AI generation attempts: {attempts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
