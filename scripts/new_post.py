#!/usr/bin/env python3
"""Create a new post skeleton in _posts/.

Example:
  python3 scripts/new_post.py "Lemon Ricotta Cake" --tags "Recipes,Dessert,Cakes, Slices and Biscuits"
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_site import POSTS_DIR, dump_front_matter, slugify


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new Leave Room for Dessert post")
    parser.add_argument("title")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--tags", default="Recipes", help='Comma-separated tags, e.g. "Recipes,Dessert,Chocolate"')
    parser.add_argument("--image", default="", help="Path under the site, e.g. /assets/uploads/2026/08/cake.jpg")
    args = parser.parse_args()
    slug = slugify(args.title)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if "Recipes" not in tags:
        # Keep it on the recipe index unless you pass --tags without Recipes on purpose
        pass
    body = (
        "<p>Write the story here. Add photos with:</p>\n"
        '<p><img src="/assets/uploads/YYYY/MM/your-photo.jpg" alt=""></p>\n'
        f"<p><strong>{args.title}</strong></p>\n"
        "<p>List ingredients here.</p>\n"
        "<p>Write the method here.</p>\n"
    )
    meta = {
        "title": args.title,
        "date": args.date,
        "permalink": f"/{slug}/",
        "image": args.image,
        "excerpt": "",
        "tags": tags,
    }
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = POSTS_DIR / f"{args.date}-{slug}.html"
    if dest.exists():
        raise SystemExit(f"Already exists: {dest}")
    dest.write_text(dump_front_matter(meta, body), encoding="utf-8")
    print(f"Created {dest.relative_to(POSTS_DIR.parent)}")
    print("Add photos under assets/uploads/, then run: python3 scripts/build_site.py")


if __name__ == "__main__":
    main()
