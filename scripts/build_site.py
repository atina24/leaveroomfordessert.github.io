#!/usr/bin/env python3
"""Build the Leave Room for Dessert static site from `_posts/` source files.

First run extracts posts from the original HTML export if `_posts` is empty.
After that, edit files in `_posts/` and `_pages/` and run this script again.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "_posts"
PAGES_DIR = ROOT / "_pages"
SKIP_DIRS = {
    "about",
    "recipes",
    "links",
    "search",
    "category",
    "page",
    "assets",
    "scripts",
    "_posts",
    "_pages",
    "_site",
    "tags",
    "2009",
    "2010",
    "2011",
    "2012",
    "2013",
    "2014",
    "2015",
    "2016",
    "2017",
    "2018",
}
RECIPE_HINTS = {
    "recipes",
    "appetizers",
    "breads",
    "breakfast",
    "budget meals",
    "cakes, slices and biscuits",
    "cheese",
    "chocolate",
    "condiments",
    "cooking class - family",
    "dessert",
    "drinks",
    "egg whites",
    "egg yolks",
    "for kids",
    "gluten free",
    "healthy eating",
    "high tea",
    "ice cream",
    "indian banquet",
    "main meals",
    "party food",
    "pastry",
    "petit fours",
    "roundup",
    "salad",
    "snacks",
    "vegetarian",
}
DROP_TAGS = {"uncategorized"}
FEATURED_TAGS = [
    "Dessert",
    "Cakes, Slices and Biscuits",
    "Chocolate",
    "Main Meals",
    "Snacks",
    "Vegetarian",
    "Breakfast",
    "Daring Bakers",
    "Cake Decorating",
    "Pastry",
]


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "tag"


def parse_pretty_date(text: str) -> datetime:
    text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", (text or "").strip())
    for fmt in ("%B %d, %Y", "%B %d %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime(2009, 1, 1)


def dump_front_matter(meta: dict, body: str) -> str:
    tags = meta["tags"]
    tag_yaml = "[" + ", ".join(json.dumps(t) for t in tags) + "]"
    title = json.dumps(meta["title"], ensure_ascii=False)
    excerpt = json.dumps(meta.get("excerpt") or "", ensure_ascii=False)
    image = json.dumps(meta.get("image") or "", ensure_ascii=False)
    return (
        "---\n"
        f"title: {title}\n"
        f"date: {meta['date']}\n"
        f"permalink: {meta['permalink']}\n"
        f"image: {image}\n"
        f"excerpt: {excerpt}\n"
        f"tags: {tag_yaml}\n"
        "---\n"
        f"{body.strip()}\n"
    )


def load_source(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"Missing front matter: {path}")
    _, fm, body = raw.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key == "tags":
            meta[key] = json.loads(val)
        elif key in {"title", "image", "excerpt", "permalink"}:
            meta[key] = json.loads(val) if val.startswith('"') else val.strip('"')
        else:
            meta[key] = val
    meta["body"] = body.strip()
    meta["slug"] = meta["permalink"].strip("/")
    meta["date_obj"] = datetime.strptime(meta["date"][:10], "%Y-%m-%d")
    meta["date_pretty"] = meta["date_obj"].strftime("%B ") + ordinal(meta["date_obj"].day) + meta["date_obj"].strftime(", %Y")
    meta["is_recipe"] = "Recipes" in meta.get("tags", [])
    meta["tag_slugs"] = [(t, slugify(t)) for t in meta.get("tags", [])]
    return meta


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def extract_posts() -> None:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for folder in sorted(ROOT.iterdir()):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name in SKIP_DIRS:
            continue
        page = folder / "index.html"
        if not page.exists():
            continue
        soup = BeautifulSoup(page.read_text(encoding="utf-8", errors="replace"), "html.parser")
        entry = soup.select_one(".entry")
        title_el = soup.select_one(".post h2")
        if not entry or not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        date_el = soup.select_one(".post small")
        date = parse_pretty_date(date_el.get_text(" ", strip=True) if date_el else "")
        tags = []
        for a in soup.select(".postmetadata a"):
            name = a.get_text(" ", strip=True)
            if name.lower() in DROP_TAGS:
                continue
            if name not in tags:
                tags.append(name)
        if any(t.lower() in RECIPE_HINTS for t in tags) and "Recipes" not in tags:
            tags.insert(0, "Recipes")
        for p in list(entry.select("p.postmetadata")):
            p.decompose()
        for a in list(entry.select("a")):
            rel = a.get("rel") or []
            rel_text = " ".join(rel) if isinstance(rel, list) else str(rel)
            if a.find("img") and "attachment" in rel_text:
                a.unwrap()
        body = "".join(str(child) for child in entry.children).strip()
        first_img = entry.find("img")
        image = first_img.get("src") if first_img else ""
        excerpt = " ".join(entry.get_text(" ", strip=True).split())[:180]
        permalink = f"/{folder.name}/"
        meta = {
            "title": title,
            "date": date.strftime("%Y-%m-%d"),
            "permalink": permalink,
            "image": image or "",
            "excerpt": excerpt,
            "tags": tags,
        }
        filename = f"{date.strftime('%Y-%m-%d')}-{folder.name}.html"
        (POSTS_DIR / filename).write_text(dump_front_matter(meta, body), encoding="utf-8")
        count += 1
    about = ROOT / "about" / "index.html"
    if about.exists():
        soup = BeautifulSoup(about.read_text(encoding="utf-8", errors="replace"), "html.parser")
        entry = soup.select_one(".entry")
        body = "".join(str(child) for child in entry.children).strip() if entry else ""
        (PAGES_DIR / "about.html").write_text(
            dump_front_matter(
                {
                    "title": "About Anita",
                    "date": "2009-01-01",
                    "permalink": "/about/",
                    "image": "/assets/uploads/2009/01/me.jpg",
                    "excerpt": "Baking is my passion, a passion best shared with others.",
                    "tags": [],
                },
                body,
            ),
            encoding="utf-8",
        )
    print(f"Extracted {count} posts into _posts/")


def esc(text: str) -> str:
    return html_lib.escape(text or "")


def nav(current: str) -> str:
    items = [("Home", "/"), ("Recipes", "/recipes/"), ("About", "/about/")]
    links = []
    for label, href in items:
        cur = ' aria-current="page"' if current == href else ""
        links.append(f'<li><a href="{href}"{cur}>{label}</a></li>')
    return "\n".join(links)


def page_shell(title: str, description: str, current: str, main: str, aside: str = "", extra_js: str = "") -> str:
    aside_html = f"<aside>{aside}</aside>" if aside else ""
    layout_class = "layout has-aside" if aside else "layout"
    js = '<script src="/assets/js/site.js"></script>' if extra_js else ""
    return f"""<!DOCTYPE html>
<html lang="en-AU">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <meta name="author" content="Anita">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,600;0,700;1,600&family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/assets/css/site.css">
  <link rel="shortcut icon" href="/favicon.ico">
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header">
    <a class="banner" href="/"><img src="/assets/images/banner.jpg" alt="Leave Room for Dessert"></a>
    <div class="wrap nav">
      <ul class="nav-links">
        {nav(current)}
      </ul>
      <form class="search-mini" action="/recipes/" method="get" role="search">
        <input type="search" name="q" placeholder="Search recipes…" aria-label="Search recipes">
        <button type="submit">Search</button>
      </form>
    </div>
  </header>
  <div class="wrap {layout_class}">
    <main id="main">{main}</main>
    {aside_html}
  </div>
  <footer class="site-footer">
    <div class="wrap">
      <p>Leave Room for Dessert — Anita’s Sydney food blog.</p>
      <p>Always leave room for dessert.</p>
    </div>
  </footer>
  {js}
</body>
</html>
"""


def card(post: dict) -> str:
    img = ""
    if post.get("image"):
        img = f'<div class="card-image"><img src="{esc(post["image"])}" alt=""></div>'
    else:
        img = '<div class="card-image"></div>'
    tags = " · ".join(post.get("tags", [])[:3])
    return f"""
<a class="card" href="{esc(post["permalink"])}" data-recipe-card data-title="{esc(post["title"])}" data-tags="{"|".join(esc(t) for t in post.get("tags", []))}" data-excerpt="{esc(post.get("excerpt", ""))}">
  {img}
  <div class="card-body">
    <p class="meta">{esc(post["date_pretty"])}{(" · " + esc(tags)) if tags else ""}</p>
    <h3>{esc(post["title"])}</h3>
    <p class="excerpt">{esc(post.get("excerpt", ""))}</p>
  </div>
</a>
"""


def recent_aside(posts: list[dict]) -> str:
    items = "".join(
        f'<li><a href="{esc(p["permalink"])}">{esc(p["title"])}<div class="meta">{esc(p["date_pretty"])}</div></a></li>'
        for p in posts[:8]
    )
    return f"<h2>Recent Posts</h2><ul class='recent-list'>{items}</ul>"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def clean_generated(keep_slugs: set[str]) -> None:
    for child in ROOT.iterdir():
        if not child.is_dir() or child.name.startswith(".") or child.name in {
            "assets", "scripts", "_posts", "_pages", "tags"
        }:
            continue
        if child.name in SKIP_DIRS or child.name in keep_slugs or child.name == "about":
            continue
        idx = child / "index.html"
        if idx.exists():
            shutil.rmtree(child)
    for old in ["links", "category", "page", "search", "2009", "2010", "2011", "2012", "2013", "2014", "2015", "2016", "2017", "2018"]:
        p = ROOT / old
        if p.exists():
            shutil.rmtree(p)
    old_css = ROOT / "assets" / "css" / "style.css"
    if old_css.exists():
        old_css.unlink()
    for name in ["kubrickbgcolor.jpg", "kubrickbgwide.jpg", "kubrickfootersquare.jpg"]:
        p = ROOT / "assets" / "images" / name
        if p.exists():
            p.unlink()


def build() -> None:
    if not any(POSTS_DIR.glob("*.html")) or not (PAGES_DIR / "about.html").exists():
        extract_posts()
    posts = [load_source(p) for p in POSTS_DIR.glob("*.html")]
    posts.sort(key=lambda p: p["date_obj"], reverse=True)
    recipes = [p for p in posts if p["is_recipe"]]
    recipes_az = sorted(recipes, key=lambda p: p["title"].casefold())
    tag_map: dict[str, list] = defaultdict(list)
    tag_names: dict[str, str] = {}
    for post in posts:
        for name, slug in post["tag_slugs"]:
            tag_map[slug].append(post)
            tag_names[slug] = name

    # Home
    home_cards = "".join(card(p) for p in posts[:9])
    tag_pills = "".join(
        f'<a class="chip" href="/tags/{slugify(name)}/">{esc(name)}</a>'
        for name in FEATURED_TAGS if slugify(name) in tag_map
    )
    home_main = f"""
<section class="hero-copy">
  <p class="kicker">A Sydney food blog</p>
  <h1>Recipes worth lingering over</h1>
  <p class="lede">Cakes, puddings, weeknight dinners and bakers’ projects from Anita’s kitchen — collected here so you can find something delicious.</p>
  <p><a class="btn" href="/recipes/">Browse all recipes</a></p>
</section>
<div class="section-head"><h2>Recent Posts</h2><a href="/recipes/">All recipes →</a></div>
<div class="card-grid">{home_cards}</div>
<div class="section-head"><h2>Browse by tag</h2><a href="/tags/">Every tag →</a></div>
<div class="filters">{tag_pills}</div>
"""
    write(ROOT / "index.html", page_shell("Leave Room for Dessert", "Anita’s food blog — cakes, desserts and homemade recipes from Sydney.", "/", home_main))

    # Recipes
    counts = Counter(t for p in recipes for t in p.get("tags", []) if t != "Recipes")
    chips = ['<button type="button" class="chip" data-tag-filter="">All</button>']
    for name, n in counts.most_common(14):
        chips.append(f'<button type="button" class="chip" data-tag-filter="{esc(name)}">{esc(name)} <span class="chip-count">{n}</span></button>')
    recipe_cards = "".join(card(p) for p in recipes_az)
    recipes_main = f"""
<section class="hero-copy">
  <p class="kicker">Recipe index</p>
  <h1>Find something to bake</h1>
  <p class="lede">Search by name, or tap a tag. There are {len(recipes)} recipes in the tin.</p>
</section>
<p><input class="recipe-search" id="recipe-search" type="search" placeholder="Search for a recipe or ingredient: e.g. pizza OR almond" aria-label="Filter recipes"></p>
<p class="meta" id="recipe-count">{len(recipes)} recipes</p>
<div class="filters">{''.join(chips)}</div>
<div class="card-grid">{recipe_cards}</div>
<p class="empty" id="recipe-empty" hidden>No recipes match that just yet. Try another word or tag.</p>
"""
    write(ROOT / "recipes" / "index.html", page_shell("Recipes — Leave Room for Dessert", "Search Anita’s recipes by name or tag.", "/recipes/", recipes_main, extra_js="1"))

    # About
    about = load_source(PAGES_DIR / "about.html")
    about_main = f"""
<section class="hero-copy">
  <p class="kicker">The baker</p>
  <h1>About Anita</h1>
</section>
<div class="article about-grid">
  <img src="/assets/uploads/2009/01/me.jpg" alt="Anita">
  <div class="entry">{about["body"]}</div>
</div>
"""
    write(ROOT / "about" / "index.html", page_shell("About Anita — Leave Room for Dessert", "About Anita, the baker behind Leave Room for Dessert.", "/about/", about_main, recent_aside(posts)))

    # Posts
    for i, post in enumerate(posts):
        older = posts[i + 1] if i + 1 < len(posts) else None
        newer = posts[i - 1] if i > 0 else None
        tags = "".join(f'<a class="tag" href="/tags/{slug}/">{esc(name)}</a>' for name, slug in post["tag_slugs"])
        prev = f'<a href="{esc(older["permalink"])}">← {esc(older["title"])}</a>' if older else "<span></span>"
        nxt = f'<a href="{esc(newer["permalink"])}">{esc(newer["title"])} →</a>' if newer else "<span></span>"
        main = f"""
<article class="article">
  <p class="kicker">{"Recipe" if post["is_recipe"] else "Story"}</p>
  <h1 class="post-title">{esc(post["title"])}</h1>
  <p class="meta">{esc(post["date_pretty"])}</p>
  <div class="tags">{tags}</div>
  <div class="entry">{post["body"]}</div>
  <nav class="pager">{prev}{nxt}</nav>
</article>
"""
        write(ROOT / post["slug"] / "index.html", page_shell(f'{post["title"]} — Leave Room for Dessert', post.get("excerpt") or post["title"], "", main, recent_aside(posts)))

    # Tags
    tag_index_items = "".join(
        f'<a class="chip" href="/tags/{slug}/">{esc(tag_names[slug])} <span class="chip-count">{len(tag_map[slug])}</span></a>'
        for slug in sorted(tag_map, key=lambda s: tag_names[s].casefold())
    )
    write(
        ROOT / "tags" / "index.html",
        page_shell(
            "Tags — Leave Room for Dessert",
            "Browse posts by tag.",
            "",
            f'<section class="hero-copy"><p class="kicker">Browse</p><h1>Tags</h1><p class="lede">Every post can have as many tags as you like. Add them in the post’s front matter.</p></section><div class="filters">{tag_index_items}</div>',
        ),
    )
    for slug, tagged in tag_map.items():
        cards = "".join(card(p) for p in tagged)
        write(
            ROOT / "tags" / slug / "index.html",
            page_shell(
                f'{tag_names[slug]} — Leave Room for Dessert',
                f'Posts tagged {tag_names[slug]}.',
                "",
                f'<section class="hero-copy"><p class="kicker">Tag</p><h1>{esc(tag_names[slug])}</h1><p class="lede">{len(tagged)} post{"s" if len(tagged)!=1 else ""}.</p></section><div class="card-grid">{cards}</div>',
            ),
        )

    search = [
        {"title": p["title"], "url": p["permalink"], "date": p["date_pretty"], "tags": p["tags"], "excerpt": p.get("excerpt", "")}
        for p in posts
    ]
    write(ROOT / "search.json", json.dumps(search, ensure_ascii=False, indent=2))
    write(
        ROOT / "404.html",
        page_shell(
            "Not found — Leave Room for Dessert",
            "That page is not in the kitchen.",
            "/",
            '<section class="hero-copy"><p class="kicker">404</p><h1>Nothing baking here</h1><p class="lede">That page has wandered off. Try the recipe index, or head home for something recent.</p><p><a class="btn" href="/recipes/">Browse recipes</a></p></section>',
        ),
    )
    keep = {p["slug"] for p in posts} | {"about", "recipes", "tags"}
    clean_generated(keep)
    print(f"Built {len(posts)} posts, {len(recipes)} recipes, {len(tag_map)} tags.")


if __name__ == "__main__":
    build()
