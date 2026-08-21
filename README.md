# Leave Room for Dessert — site handbook

This is Anita’s food blog, rebuilt as a static website for GitHub Pages.  
The live look comes from files in `_posts/` and `_pages/`. After you change those, you rebuild, then commit and push.

## Everyday workflow

1. Edit or add a post in `_posts/`.
2. Put any new photos in `assets/uploads/YYYY/MM/`.
3. Rebuild:

```bash
cd /Users/nvonkorff/Work/git_repositories/leaveroomfordessert.github.io
python3 scripts/build_site.py
```

4. Preview:

```bash
python3 -m http.server 8000
```

Open http://127.0.0.1:8000/

5. Commit on the `redesign` branch (or `main` once you merge) and push.

You need Python 3 with BeautifulSoup (`pip3 install beautifulsoup4`).

## How a post is stored

Each post is an HTML file with a small header (YAML front matter) at the top:

```yaml
---
title: "Banana Bread"
date: 2009-06-07
permalink: /banana-bread/
image: "/assets/uploads/2009/06/bananabread-15.jpg"
excerpt: "I don’t like wasting food."
tags: ["Recipes", "Cakes, Slices and Biscuits", "Snacks"]
---
<p>Story and method go here.</p>
<p><img src="/assets/uploads/2009/06/bananabread-15.jpg" alt="Banana bread"></p>
```

| Field | What it does |
| --- | --- |
| `title` | Headline on the post, cards, and browser tab |
| `date` | `YYYY-MM-DD`. Newest dates appear first on Home |
| `permalink` | Public URL, e.g. `/banana-bread/` |
| `image` | Card thumbnail on Home and Recipes. Use a landscape photo if you can |
| `excerpt` | Short teaser on cards |
| `tags` | How the post is grouped. See below |

The filename should be `YYYY-MM-DD-url-slug.html`, matching the date and permalink.

## Create a new post

Shortcut:

```bash
python3 scripts/new_post.py "Lemon Ricotta Cake" --tags "Recipes,Dessert,Cakes, Slices and Biscuits"
```

That writes a starter file in `_posts/`. Open it, paste the story, ingredients and method, and point `image` at a photo.

Then:

1. Copy photos into `assets/uploads/2026/08/` (use the real year/month).
2. In the post, add:

   ```html
   <p><img src="/assets/uploads/2026/08/lemon-ricotta.jpg" alt="Lemon ricotta cake"></p>
   ```

3. Run `python3 scripts/build_site.py`.
4. Refresh the local preview.

To keep a post **off** the Recipes page, omit the `Recipes` tag (use it for stories, parties, or decorating posts that are not really recipes).

## Tags (replaces the old Categories)

There is no separate categories database. Tags live on the post.

- Add as many as you like in the `tags` list.
- The **Recipes** tag puts the post on `/recipes/`.
- Every other tag gets a page at `/tags/tag-name/`, for example `/tags/chocolate/`.
- Home shows a handful of popular tags. `/tags/` lists all of them.

Useful existing tags: `Dessert`, `Cakes, Slices and Biscuits`, `Chocolate`, `Main Meals`, `Snacks`, `Vegetarian`, `Breakfast`, `Daring Bakers`, `Cake Decorating`, `Pastry`.

You can invent new ones (`For kids`, `Gluten Free`, `Ice Cream`). After a rebuild they appear automatically.

To rename a tag, change the text in every post that uses it, then rebuild.

## Photos

Keep originals in `assets/uploads/YYYY/MM/`. Use paths that start with `/assets/uploads/...` so they work on GitHub Pages and with a custom domain.

The header banner is `assets/images/banner.jpg` (the original banner with the dark border trimmed). Swap that file if you ever re-shoot the header; keep the same filename.

## Pages

| URL | Source |
| --- | --- |
| `/` | Built from the newest posts |
| `/recipes/` | Every post tagged `Recipes`, with live search and tag chips |
| `/about/` | `_pages/about.html` |
| `/tags/` | Built from all tags in use |
| `/banana-bread/` | `_posts/2009-06-07-banana-bread.html` |

Edit About by changing `_pages/about.html`, then rebuild.

## What the rebuild does

`scripts/build_site.py` reads `_posts/` and `_pages/` and writes the public HTML (`index.html`, `recipes/`, `about/`, each post folder, tag pages). It does not change your `_posts/` files.

The first time it ran, it copied the old WordPress export into `_posts/`. You should not need that step again.

## GitHub Pages

The public site is the HTML at the repo root (plus `assets/`). `.nojekyll` tells GitHub not to run Jekyll.

After a rebuild:

```bash
git add -A
git status
git commit -m "Add lemon ricotta cake"
git push
```

If this work is still on the `redesign` branch, merge it to `main` when you are happy, then push `main`.

## Preview checklist

- Home shows the banner, recent post cards, and tag shortcuts
- Recipes search filters as you type
- Tag chips narrow the list
- A recipe page shows the story, photos, tags, and Recent Posts
- About still has Anita’s photo and note
- Nothing mentions WordPress, email subscribe, archives, or the old blogroll
