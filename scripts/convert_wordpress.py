#!/usr/bin/env python3
"""Convert Leave Room for Dessert from WordPress into a GitHub Pages site.

The original theme used relative nav links (about/, recipes/, links/). Static
crawlers followed those from every post and looped forever. This script reads
the WordPress REST API (and a local wget dump for images), then writes a
static site with root-absolute URLs that GitHub Pages can serve as-is.

Post comments are intentionally omitted; only titles, dates, body content,
images, and categories are converted.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_SITE_URL = "http://leaveroomfordessert.com"
DEFAULT_DUMP = Path("/Users/nvonkorff/website_backups/leaveroomfordessert")
THEME_CSS_REL = Path("wp-content/themes/leaveroomfordessert/style.css")
THEME_IMAGES_REL = Path("wp-content/themes/leaveroomfordessert/images")
THEME_FAVICON_REL = Path("wp-content/themes/leaveroomfordessert/favicon.ico")
RECIPES_CATEGORY_ID = 3
POSTS_PER_PAGE = 10
REQUEST_TIMEOUT = 45
USER_AGENT = "LeaveRoomForDessert-GitHubPagesConverter/1.0"

SITE_HOSTS = {
    "leaveroomfordessert.com",
    "www.leaveroomfordessert.com",
}


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL)
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP)
    parser.add_argument("--output", type=Path, default=here)
    parser.add_argument("--cache", type=Path, default=here / "scripts" / "cache")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--base-url", default="", help="Prefix for project pages, e.g. /repo-name")
    return parser.parse_args()


class Converter:
    def __init__(self, args: argparse.Namespace) -> None:
        self.site_url = args.site_url.rstrip("/")
        self.dump = args.dump
        self.output = args.output
        self.cache = args.cache
        self.refresh_cache = args.refresh_cache
        self.skip_images = args.skip_images
        self.base = args.base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/html"})
        self.posts: list[dict[str, Any]] = []
        self.pages: list[dict[str, Any]] = []
        self.categories: list[dict[str, Any]] = []
        self.cat_by_id: dict[int, dict[str, Any]] = {}
        self.id_to_path: dict[int, str] = {}
        self.slug_to_post: dict[str, dict[str, Any]] = {}
        self.recipe_cat_ids: set[int] = set()
        self.missing_images: list[str] = []
        self.report: list[str] = []

    def url(self, path: str) -> str:
        if not path:
            return self.base + "/"
        if path.startswith("#") or path.startswith("mailto:") or path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.base + path

    def log(self, message: str) -> None:
        print(message, flush=True)
        self.report.append(message)

    def cache_path(self, key: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", key)
        return self.cache / f"{safe}.json"

    def get_json(self, url: str, cache_key: str) -> Any:
        path = self.cache_path(cache_key)
        if path.exists() and not self.refresh_cache:
            return json.loads(path.read_text(encoding="utf-8"))
        last_error = None
        for attempt in range(1, 6):
            try:
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding="utf-8")
                time.sleep(0.15)
                return data
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(attempt * 1.5)
        raise RuntimeError(f"Failed to fetch {url}: {last_error}")

    def get_json_pages(self, endpoint: str, cache_prefix: str) -> list[Any]:
        items: list[Any] = []
        page = 1
        while True:
            sep = "&" if "?" in endpoint else "?"
            url = f"{self.site_url}{endpoint}{sep}per_page=100&page={page}"
            data = self.get_json(url, f"{cache_prefix}-page-{page}")
            if not data:
                break
            if isinstance(data, dict) and data.get("code"):
                break
            items.extend(data)
            if len(data) < 100:
                break
            page += 1
            self.log(f"  fetched {cache_prefix} page {page - 1} ({len(items)} items)")
        return items

    def fetch_wordpress(self) -> None:
        self.cache.mkdir(parents=True, exist_ok=True)
        self.log("Fetching categories, pages, and posts from WordPress…")
        self.categories = self.get_json_pages("/wp-json/wp/v2/categories", "categories")
        self.pages = self.get_json_pages("/wp-json/wp/v2/pages", "pages")
        self.posts = self.get_json_pages("/wp-json/wp/v2/posts", "posts")
        self.posts.sort(key=lambda p: p["date"], reverse=True)
        self.cat_by_id = {int(c["id"]): c for c in self.categories}
        self.recipe_cat_ids = self.descendant_ids(RECIPES_CATEGORY_ID)
        for post in self.posts:
            slug = unquote(post.get("slug") or f"post-{post['id']}").strip("/")
            post["_slug"] = slug
            post["_path"] = f"/{slug}/"
            post["_title"] = clean_text(post["title"]["rendered"])
            post["_date"] = parse_wp_date(post["date"])
            post["_cats"] = [self.cat_by_id[cid] for cid in post.get("categories", []) if cid in self.cat_by_id]
            self.id_to_path[int(post["id"])] = post["_path"]
            self.slug_to_post[slug] = post
        for page in self.pages:
            slug = unquote(page.get("slug") or f"page-{page['id']}").strip("/")
            page["_slug"] = slug
            page["_path"] = f"/{slug}/"
            page["_title"] = clean_text(page["title"]["rendered"])
            self.id_to_path[int(page["id"])] = page["_path"]
        self.log(
            f"Loaded {len(self.posts)} posts, {len(self.pages)} pages, "
            f"{len(self.categories)} categories (comments omitted)"
        )

    def descendant_ids(self, root_id: int) -> set[int]:
        ids = {root_id}
        changed = True
        while changed:
            changed = False
            for cat in self.categories:
                if cat["parent"] in ids and cat["id"] not in ids:
                    ids.add(cat["id"])
                    changed = True
        return ids

    def category_path(self, cat: dict[str, Any]) -> str:
        parts = [cat["slug"]]
        parent_id = cat.get("parent") or 0
        seen = set()
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            parent = self.cat_by_id.get(parent_id)
            if not parent:
                break
            parts.append(parent["slug"])
            parent_id = parent.get("parent") or 0
        return "/category/" + "/".join(reversed(parts)) + "/"

    def rewrite_url(self, url: str) -> str:
        if not url:
            return url
        url = html.unescape(url.strip())
        if url.startswith(("mailto:", "javascript:", "tel:", "#")):
            return url
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if parsed.scheme in ("http", "https") and host and host not in SITE_HOSTS:
            return url
        path = unquote(parsed.path or "/")
        query = parse_qs(parsed.query)
        if "p" in query:
            try:
                pid = int(query["p"][0])
            except (TypeError, ValueError):
                pid = None
            if pid in self.id_to_path:
                rewritten = self.id_to_path[pid]
                if parsed.fragment:
                    rewritten += "#" + parsed.fragment
                return self.url(rewritten)
        if "attachment_id" in query:
            return url
        if path.startswith("/wp-content/uploads/"):
            path = "/assets/uploads/" + path[len("/wp-content/uploads/") :]
        elif path.startswith("/wp-content/themes/leaveroomfordessert/"):
            rest = path[len("/wp-content/themes/leaveroomfordessert/") :]
            if rest == "favicon.ico" or rest.endswith("/favicon.ico"):
                path = "/favicon.ico"
            elif rest.startswith("images/"):
                path = "/assets/" + rest
            elif rest == "style.css":
                path = "/assets/css/style.css"
        if path in {"/feed/", "/feed/atom/", "/xmlrpc.php", "/comments/feed/"}:
            path = "/"
        if re.search(r"/(feed|trackback)/?$", path):
            path = re.sub(r"/(feed|trackback)/?$", "/", path)
        if path.endswith("/about/") and path != "/about/":
            path = "/about/"
        if path.endswith("/recipes/") and path != "/recipes/":
            path = "/recipes/"
        if path.endswith("/links/") and path != "/links/":
            path = "/links/"
        if parsed.fragment:
            path += "#" + parsed.fragment
        return self.url(path)

    def clean_html(self, raw: str) -> str:
        if not raw:
            return ""
        raw = raw.replace(self.site_url, "")
        raw = raw.replace("http://www.leaveroomfordessert.com", "")
        raw = raw.replace("https://www.leaveroomfordessert.com", "")
        raw = raw.replace("https://leaveroomfordessert.com", "")
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        for img in soup.find_all("img"):
            if img.get("src"):
                img["src"] = self.rewrite_url(img["src"])
            if img.get("srcset"):
                parts = []
                for chunk in img["srcset"].split(","):
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    bits = chunk.split()
                    bits[0] = self.rewrite_url(bits[0])
                    parts.append(" ".join(bits))
                img["srcset"] = ", ".join(parts)
            for attr in ("fetchpriority", "decoding", "data-id", "data-attachment-id"):
                if attr in img.attrs:
                    del img.attrs[attr]
        for anchor in list(soup.find_all("a")):
            href = anchor.get("href")
            if not href:
                continue
            if "attachment_id=" in href or "/?attachment_id=" in href:
                img = anchor.find("img")
                if img:
                    anchor.replace_with(img)
                    continue
            rewritten = self.rewrite_url(href)
            if rewritten == href and "attachment_id=" in href:
                img = anchor.find("img")
                if img:
                    anchor.replace_with(img)
                    continue
            anchor["href"] = rewritten
        return str(soup)

    def extract_dump_page_html(self, slug: str, selector: str = "div.entry") -> str:
        path = self.dump / slug / "index.html"
        if not path.exists():
            return ""
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        entry = soup.select_one(selector)
        if not entry:
            return ""
        return self.clean_html("".join(str(child) for child in entry.children))

    def posts_in_category(self, cat_id: int) -> list[dict[str, Any]]:
        ids = self.descendant_ids(cat_id) if cat_id == RECIPES_CATEGORY_ID else {cat_id}
        # Child category pages should list only that category, not descendants,
        # except Recipes which historically included children.
        if cat_id != RECIPES_CATEGORY_ID:
            ids = {cat_id}
        return [p for p in self.posts if set(p.get("categories") or []) & ids]

    def recipe_posts(self) -> list[dict[str, Any]]:
        found = [p for p in self.posts if set(p.get("categories") or []) & self.recipe_cat_ids]
        return sorted(found, key=lambda p: p["_title"].casefold())

    def filed_under(self, post: dict[str, Any]) -> str:
        links = []
        for cat in sorted(post["_cats"], key=lambda c: c["name"].casefold()):
            href = self.url(self.category_path(cat))
            links.append(f'<a href="{href}" rel="category tag">{html.escape(cat["name"])}</a>')
        return ", ".join(links)

    def pretty_date(self, dt: datetime) -> str:
        return f"{dt.strftime('%B')} {ordinal(dt.day)}, {dt.year}"

    def layout(
        self,
        *,
        title: str,
        description: str,
        content: str,
        canonical: str,
    ) -> str:
        page_title = "Leave Room for Dessert" if title == "Leave Room for Dessert" else f"{title} « Leave Room for Dessert"
        desc = html.escape(description or "Leave Room for Dessert - Anita's Food Blog")
        return f"""<!DOCTYPE html>
<html lang="en-AU">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page_title)}</title>
<meta http-equiv="author" content="Anita">
<meta name="description" content="{desc}">
<meta name="keywords" content="baking, dessert, cooking, blog, Anita, food, chocolate, recipes, home made, Leave Room for Dessert">
<link rel="stylesheet" href="{self.url("/assets/css/style.css")}" type="text/css" media="screen">
<link rel="shortcut icon" href="{self.url("/favicon.ico")}">
<link rel="canonical" href="{self.url(canonical)}">
</head>
<body>
<div id="page">
<div id="header" onclick="location.href='{self.url("/")}'" style="cursor: pointer;">
  <div id="headerimg">
    <h1><a href="{self.url("/")}"></a></h1>
  </div>
</div>
<div id="navmenu">
<ul>
  <table bgcolor="#120800" width="740">
     <tr height="25">
       <td><li><a href="{self.url("/")}">HOME</a></li></td>
       <td><li><a href="{self.url("/about/")}">ABOUT</a></li></td>
       <td><li><a href="{self.url("/recipes/")}">RECIPES</a></li></td>
       <td width="100%"><li><a href="{self.url("/links/")}">LINKS</a></li></td>
     </tr>
   </table>
</ul>
</div>
<hr>
{content}
{self.render_sidebar()}
<div id="footer">
  <p>Leave Room for Dessert<br>
  An archive of Anita’s food blog, originally published 2009–2018.</p>
</div>
</div>
</body>
</html>
"""

    def render_sidebar(self) -> str:
        recent = []
        for post in self.posts[:10]:
            recent.append(f'<li><a href="{self.url(post["_path"])}">{html.escape(post["_title"])}</a></li>')
        archives = []
        by_month: dict[str, list] = defaultdict(list)
        for post in self.posts:
            key = post["_date"].strftime("%Y-%m")
            by_month[key].append(post)
        for key in sorted(by_month.keys(), reverse=True):
            dt = datetime.strptime(key, "%Y-%m")
            label = dt.strftime("%B %Y")
            href = self.url(f"/{dt.strftime('%Y/%m')}/")
            archives.append(f'<li><a href="{href}">{label}</a>&nbsp;({len(by_month[key])})</li>')

        def cat_items(parent_id: int) -> str:
            children = [
                c
                for c in self.categories
                if (c.get("parent") or 0) == parent_id and (c.get("count") or 0) > 0
            ]
            children.sort(key=lambda c: c["name"].casefold())
            if not children:
                return ""
            bits = []
            for cat in children:
                href = self.url(self.category_path(cat))
                nested = cat_items(cat["id"])
                item = f'<li><a href="{href}">{html.escape(cat["name"])}</a> ({cat["count"]})'
                if nested:
                    item += f'<ul class="children">{nested}</ul>'
                item += "</li>"
                bits.append(item)
            return "\n".join(bits)

        return f"""
<div id="sidebar">
  <ul>
    <li>
      <h2>Pages</h2>
      <ul>
        <li><a href="{self.url("/about/")}">About Me</a></li>
        <li><a href="{self.url("/links/")}">Links</a></li>
        <li><a href="{self.url("/recipes/")}">Recipes</a></li>
      </ul>
    </li>
    <li>
      <form id="searchform" class="searchform" action="{self.url("/search/")}" method="get">
        <div>
          <label class="screen-reader-text" for="s">Search for:</label>
          <input type="text" value="" name="s" id="s">
          <input type="submit" id="searchsubmit" value="Search">
        </div>
      </form>
    </li>
    <li>
      <h2>About Me…</h2>
      <div class="textwidget">
        <img src="{self.url("/assets/uploads/2010/03/AnitaLRfD1.jpg")}" width="180" alt="Anita">
        <p>Baking is my passion, a passion best shared with others.</p>
        <p>I live in Sydney, Australia, close to family and friends and love a good meal and chat. Desserts, cakes and all things sweet attract my attention... that's why I always leave room for dessert... <a href="{self.url("/about/")}">Read more about me</a></p>
        <p>P.S. Thanks for visiting my blog!</p>
        <p>Cheers,</p>
        <p>Anita</p>
      </div>
    </li>
    <li>
      <h2>Recent Posts</h2>
      <ul>
        {''.join(recent)}
      </ul>
    </li>
    <li>
      <h2>Daring Bakers</h2>
      <div class="textwidget">
        <p>I'm a proud member of the Daring Bakers</p>
        <p><a href="http://www.thedaringkitchen.com/"><img src="{self.url("/assets/uploads/2009/11/vanilla_w180x180.jpg")}" width="150" alt="Daring Bakers"></a></p>
      </div>
    </li>
    <li>
      <h2>Archives</h2>
      <ul>
        {''.join(archives)}
      </ul>
    </li>
    <li>
      <h2>Categories</h2>
      <ul>
        {cat_items(0)}
      </ul>
    </li>
  </ul>
</div>
"""

    def write(self, rel: str, text: str) -> None:
        path = self.output / rel.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_posts(self) -> None:
        self.log("Writing posts…")
        for child in self.output.iterdir():
            if child.is_dir() and "%" in child.name:
                shutil.rmtree(child)
        chronological = list(reversed(self.posts))  # oldest first for prev/next
        index_by_id = {p["id"]: i for i, p in enumerate(chronological)}
        for post in self.posts:
            i = index_by_id[post["id"]]
            older = chronological[i - 1] if i > 0 else None
            newer = chronological[i + 1] if i + 1 < len(chronological) else None
            nav_left = f'&laquo; <a href="{self.url(older["_path"])}" rel="prev">{html.escape(older["_title"])}</a>' if older else ""
            nav_right = f'<a href="{self.url(newer["_path"])}" rel="next">{html.escape(newer["_title"])}</a> &raquo;' if newer else ""
            content_html = self.clean_html(post.get("content", {}).get("rendered", ""))
            body = f"""
<div id="content" class="narrowcolumn">
  <div class="navigation">
    <div class="alignleft">{nav_left}</div>
    <div class="alignright">{nav_right}</div>
  </div>
  <div class="post" id="post-{post["id"]}">
    <h2>{html.escape(post["_title"])}</h2>
    <small>{self.pretty_date(post["_date"])}</small>
    <div class="entry">
      {content_html}
      <p class="postmetadata"><small>Filed under {self.filed_under(post)}.</small></p>
    </div>
  </div>
</div>
"""
            page = self.layout(
                title=post["_title"],
                description=post["_title"],
                content=body,
                canonical=post["_path"],
            )
            self.write(f"{post['_slug']}/index.html", page)
        self.log(f"Wrote {len(self.posts)} posts")

    def write_home_and_archives(self) -> None:
        self.log("Writing home, pagination, and monthly archives…")
        pages = chunked(self.posts, POSTS_PER_PAGE)
        for page_num, posts in enumerate(pages, start=1):
            items = [self.render_home_post(p) for p in posts]
            older = newer = ""
            if page_num < len(pages):
                older = f'<a href="{self.url(f"/page/{page_num + 1}/")}">&laquo; Older Entries</a>'
            if page_num == 2:
                newer = f'<a href="{self.url("/")}">Newer Entries &raquo;</a>'
            elif page_num > 2:
                newer = f'<a href="{self.url(f"/page/{page_num - 1}/")}">Newer Entries &raquo;</a>'
            body = f"""
<div id="content" class="narrowcolumn">
  {''.join(items)}
  <div class="navigation">
    <div class="alignleft">{older}</div>
    <div class="alignright">{newer}</div>
  </div>
</div>
"""
            html_page = self.layout(
                title="Leave Room for Dessert",
                description="Leave Room for Dessert - Anita's Food Blog",
                content=body,
                canonical="/" if page_num == 1 else f"/page/{page_num}/",
            )
            if page_num == 1:
                self.write("index.html", html_page)
            else:
                self.write(f"page/{page_num}/index.html", html_page)

        by_month: dict[str, list] = defaultdict(list)
        for post in self.posts:
            by_month[post["_date"].strftime("%Y/%m")].append(post)
        for key, posts in by_month.items():
            dt = datetime.strptime(key, "%Y/%m")
            items = [self.render_home_post(p) for p in posts]
            body = f"""
<div id="content" class="narrowcolumn">
  <h2 class="pagetitle">{dt.strftime('%B %Y')}</h2>
  {''.join(items)}
</div>
"""
            page = self.layout(
                title=dt.strftime("%B %Y"),
                description=f"Posts from {dt.strftime('%B %Y')}",
                content=body,
                canonical=f"/{key}/",
            )
            self.write(f"{key}/index.html", page)

    def render_home_post(self, post: dict[str, Any]) -> str:
        content_html = self.clean_html(post.get("content", {}).get("rendered", ""))
        return f"""
<div class="post" id="post-{post["id"]}">
  <h2><a href="{self.url(post["_path"])}" rel="bookmark">{html.escape(post["_title"])}</a></h2>
  <small>{self.pretty_date(post["_date"])}</small>
  <div class="entry">
    {content_html}
  </div>
  <p class="postmetadata"> Posted in {self.filed_under(post)}</p>
  <hr>
</div>
"""

    def write_static_pages(self) -> None:
        self.log("Writing About, Links, Recipes, categories, search, and 404…")
        about = next((p for p in self.pages if p.get("slug") == "about"), None)
        about_html = self.clean_html(about.get("content", {}).get("rendered", "")) if about else ""
        if not about_html.strip():
            about_html = self.extract_dump_page_html("about")
        about_body = f"""
<div id="content" class="narrowcolumn">
  <div class="post" id="post-2">
    <h2>About Me</h2>
    <div class="entry">{about_html}</div>
  </div>
</div>
"""
        self.write(
            "about/index.html",
            self.layout(title="About Me", description="About Anita", content=about_body, canonical="/about/"),
        )

        links_html = self.extract_dump_page_html("links", selector="#content")
        if links_html:
            soup = BeautifulSoup(links_html, "html.parser")
            for sidebar in soup.select("#sidebar"):
                sidebar.decompose()
            links_inner = "".join(str(child) for child in soup.children)
        else:
            links_inner = "<h2>Links</h2>"
        links_body = f'<div id="content" class="narrowcolumn">{links_inner}</div>'
        self.write(
            "links/index.html",
            self.layout(title="Links", description="Links", content=links_body, canonical="/links/"),
        )

        recipes = self.recipe_posts()
        items = [
            f'<h4><a href="{self.url(p["_path"])}">{html.escape(p["_title"])}</a></h4>'
            for p in recipes
        ]
        recipes_body = f"""
<div id="content" class="narrowcolumn">
  <h2>Recipes</h2>
  <p>An A–Z of recipes from Leave Room for Dessert. Type to filter the list.</p>
  <p><input type="search" id="recipe-filter" placeholder="Filter recipes…" aria-label="Filter recipes"></p>
  <div id="recipe-list">
    {''.join(items)}
  </div>
</div>
<script>
document.getElementById('recipe-filter').addEventListener('input', function () {{
  var q = this.value.toLowerCase();
  document.querySelectorAll('#recipe-list h4').forEach(function (row) {{
    row.style.display = row.textContent.toLowerCase().indexOf(q) === -1 ? 'none' : '';
  }});
}});
</script>
"""
        self.write(
            "recipes/index.html",
            self.layout(
                title="Recipes",
                description="Recipe index from Leave Room for Dessert",
                content=recipes_body,
                canonical="/recipes/",
            ),
        )

        for cat in self.categories:
            if not cat.get("count"):
                continue
            posts = self.posts_in_category(int(cat["id"]))
            if cat["id"] == RECIPES_CATEGORY_ID:
                posts = self.recipe_posts()
            listing = [self.render_home_post(p) for p in posts]
            path = self.category_path(cat)
            body = f"""
<div id="content" class="narrowcolumn">
  <h2 class="pagetitle">Category: {html.escape(cat["name"])}</h2>
  {''.join(listing) if listing else "<p>No posts in this category.</p>"}
</div>
"""
            self.write(
                path.lstrip("/") + "index.html",
                self.layout(
                    title=cat["name"],
                    description=f"Category: {cat['name']}",
                    content=body,
                    canonical=path,
                ),
            )

        search_records = []
        for post in self.posts:
            text = BeautifulSoup(post.get("content", {}).get("rendered", ""), "html.parser").get_text(" ", strip=True)
            search_records.append(
                {
                    "title": post["_title"],
                    "url": self.url(post["_path"]),
                    "date": self.pretty_date(post["_date"]),
                    "excerpt": text[:240],
                }
            )
        self.write("search.json", json.dumps(search_records, ensure_ascii=False, indent=2))
        search_body = f"""
<div id="content" class="narrowcolumn">
  <h2>Search</h2>
  <p><input type="search" id="q" placeholder="Search posts and recipes…" style="width:100%;padding:6px;"></p>
  <div id="results"></div>
</div>
<script>
fetch('{self.url("/search.json")}').then(function (r) {{ return r.json(); }}).then(function (data) {{
  var params = new URLSearchParams(window.location.search);
  var box = document.getElementById('q');
  var initial = params.get('s') || '';
  box.value = initial;
  function run() {{
    var q = box.value.toLowerCase().trim();
    var out = document.getElementById('results');
    if (!q) {{ out.innerHTML = '<p>Type a word to search the archive.</p>'; return; }}
    var hits = data.filter(function (item) {{
      return (item.title + ' ' + item.excerpt).toLowerCase().indexOf(q) !== -1;
    }});
    if (!hits.length) {{ out.innerHTML = '<p>No matching posts.</p>'; return; }}
    out.innerHTML = hits.map(function (item) {{
      return '<h4><a href="' + item.url + '">' + item.title + '</a></h4><small>' + item.date + '</small><p>' + item.excerpt + '</p>';
    }}).join('');
  }}
  box.addEventListener('input', run);
  run();
}});
</script>
"""
        self.write(
            "search/index.html",
            self.layout(title="Search", description="Search the archive", content=search_body, canonical="/search/"),
        )

        not_found = self.layout(
            title="Not Found",
            description="Page not found",
            content='<div id="content" class="narrowcolumn"><h2 class="center">Not Found</h2><p class="center">Sorry, but you are looking for something that isn\'t here.</p><p class="center"><a href="' + self.url("/") + '">Back to the home page</a></p></div>',
            canonical="/404.html",
        )
        self.write("404.html", not_found)

    def copy_assets(self) -> None:
        self.log("Copying theme assets and uploads…")
        css_src = self.dump / THEME_CSS_REL
        images_src = self.dump / THEME_IMAGES_REL
        favicon_src = self.dump / THEME_FAVICON_REL
        uploads_src = self.dump / "wp-content" / "uploads"
        css_dst = self.output / "assets" / "css" / "style.css"
        images_dst = self.output / "assets" / "images"
        uploads_dst = self.output / "assets" / "uploads"
        css_dst.parent.mkdir(parents=True, exist_ok=True)
        css_text = css_src.read_text(encoding="utf-8", errors="replace")
        css_text = css_text.replace(
            "/wp-content/themes/leaveroomfordessert/images/",
            "/assets/images/",
        )
        css_text = css_text.replace("url('images/", "url('../images/")
        css_text = css_text.replace('url("images/', 'url("../images/')
        css_text += EXTRA_CSS
        css_dst.write_text(css_text, encoding="utf-8")
        if images_dst.exists():
            shutil.rmtree(images_dst)
        shutil.copytree(images_src, images_dst)
        shutil.copy2(favicon_src, self.output / "favicon.ico")
        if self.skip_images:
            return
        if uploads_dst.exists():
            shutil.rmtree(uploads_dst)
        def ignore(directory: str, names: list[str]) -> list[str]:
            if Path(directory).name == "uploads" and "simply-static" in names:
                return ["simply-static"]
            return []
        shutil.copytree(uploads_src, uploads_dst, ignore=ignore)

    def fill_missing_images(self) -> None:
        if self.skip_images:
            return
        self.log("Checking for missing images referenced by posts…")
        html_files = list(self.output.rglob("*.html"))
        urls = set()
        for path in html_files:
            soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
            for img in soup.find_all("img"):
                if img.get("src"):
                    urls.add(img["src"])
                if img.get("srcset"):
                    for chunk in img["srcset"].split(","):
                        bits = chunk.strip().split()
                        if bits:
                            urls.add(bits[0])
        downloaded = 0
        for src in sorted(urls):
            if src.startswith(("http://", "https://", "data:", "mailto:")):
                continue
            rel = src[len(self.base) :] if self.base and src.startswith(self.base) else src
            local = self.output / rel.lstrip("/")
            if local.exists():
                continue
            remote = urljoin(self.site_url + "/", rel.replace("/assets/uploads/", "/wp-content/uploads/").lstrip("/"))
            try:
                response = self.session.get(remote, timeout=REQUEST_TIMEOUT)
                if response.status_code == 200 and response.content:
                    local.parent.mkdir(parents=True, exist_ok=True)
                    local.write_bytes(response.content)
                    downloaded += 1
                    time.sleep(0.05)
                    continue
            except Exception:  # noqa: BLE001
                pass
            self.missing_images.append(src)
        self.log(f"Downloaded {downloaded} missing images; {len(self.missing_images)} still missing")

    def write_meta_files(self) -> None:
        (self.output / ".nojekyll").write_text("", encoding="utf-8")
        robots = "User-agent: *\nAllow: /\n"
        self.write("robots.txt", robots)
        report_path = self.output / "CONVERSION_REPORT.md"
        lines = [
            "# Conversion report",
            "",
            f"- Posts: {len(self.posts)}",
            f"- Recipe posts: {len(self.recipe_posts())}",
            f"- Pages: {len(self.pages)}",
            f"- Categories: {len(self.categories)}",
            "- Comments: omitted",
            f"- Missing images: {len(self.missing_images)}",
            "",
        ]
        if self.missing_images:
            lines.append("## Missing images")
            lines.extend(f"- `{src}`" for src in self.missing_images)
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(self) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        self.fetch_wordpress()
        self.copy_assets()
        self.write_posts()
        self.write_home_and_archives()
        self.write_static_pages()
        self.fill_missing_images()
        self.write_meta_files()
        self.log("Done.")


def clean_text(value: str) -> str:
    return html.unescape(BeautifulSoup(value, "html.parser").get_text()).strip()


def parse_wp_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def chunked(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


EXTRA_CSS = """

/* GitHub Pages extras */
.screen-reader-text {
  position: absolute;
  left: -9999px;
}
#recipe-filter {
  width: 100%;
  max-width: 420px;
  padding: 6px;
  margin: 8px 0 16px;
}
img {
  max-width: 100%;
  height: auto;
}
@media (max-width: 800px) {
  #page, #header, #footer {
    width: auto;
    max-width: 760px;
  }
  .narrowcolumn {
    float: none;
    width: auto;
    padding: 0 16px 20px;
  }
  #sidebar {
    margin-left: 0;
    width: auto;
    padding: 10px 16px 20px;
    border-left: none;
  }
  #navmenu table {
    width: 100%;
  }
}
"""


if __name__ == "__main__":
    Converter(parse_args()).run()
