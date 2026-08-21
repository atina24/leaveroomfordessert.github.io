# Leave Room for Dessert (GitHub Pages)

A static copy of [leaveroomfordessert.com](http://leaveroomfordessert.com/), ready to push to GitHub Pages.

The original WordPress theme used **relative** nav links (`about/`, `recipes/`, `links/`). From a post such as `/banana-bread/`, those become `/banana-bread/about/` and so on, which is why a static-export plugin looped. This conversion uses root-absolute URLs (`/about/`, `/recipes/`, `/banana-bread/`) so that cannot happen.

## What is included

- All **233** published posts (recipe body, photos, date, categories)
- **194** recipes on `/recipes/` (A–Z list with a filter box)
- About, Links, home page, monthly archives, and category pages
- Original Kubrick-based look (banner, colours, layout)
- Local copies of the photos under `assets/uploads/`

Comments are **not** included. Search is a simple client-side filter of post titles and excerpts.

## Preview locally

From this folder:

```bash
python3 -m http.server 8000
```

Then open http://127.0.0.1:8000/ and http://127.0.0.1:8000/recipes/.

Root-absolute links (`/recipes/`) only work when you use a local server, not when you open `index.html` as a file.

## Publish to GitHub Pages

1. Create a GitHub account for the site (for example `leaveroomfordessert`).
2. Create a repository named **`leaveroomfordessert.github.io`**. That name gives you a user site at `https://leaveroomfordessert.github.io/` with no extra path prefix.
3. From this folder:

```bash
git init
git add .
git commit -m "Initial static export of Leave Room for Dessert"
git branch -M main
git remote add origin git@github.com:ACCOUNT/leaveroomfordessert.github.io.git
git push -u origin main
```

4. In the repo: **Settings → Pages → Build and deployment**. Source: **Deploy from a branch**, branch **main**, folder **/ (root)**.
5. Wait a minute, then visit `https://ACCOUNT.github.io/`.

`.nojekyll` is already in the repo so GitHub serves the HTML as-is.

### Custom domain (optional)

If you later point `leaveroomfordessert.com` at GitHub Pages:

1. Add a `CNAME` file in this folder containing only:

   ```
   leaveroomfordessert.com
   ```

2. In GitHub: **Settings → Pages → Custom domain**.
3. At the DNS host, add the records GitHub shows (usually an A record or CNAME).

If you instead use a **project** repo (`https://ACCOUNT.github.io/some-repo/`), rebuild with a prefix:

```bash
python3 scripts/convert_wordpress.py --base-url /some-repo --skip-images
```

## Rebuild from WordPress

Needs Python 3, `requests`, and `beautifulsoup4` (`pip3 install -r scripts/requirements.txt`).

```bash
python3 scripts/convert_wordpress.py
```

Useful flags:

| Flag | Purpose |
| --- | --- |
| `--skip-images` | Reuse photos already copied into `assets/uploads/` |
| `--refresh-cache` | Re-download posts from the live WordPress API |
| `--base-url /repo` | Prefix every link for a project Pages site |

The script reads http://leaveroomfordessert.com/wp-json/ and copies images from the local wget dump at `/Users/nvonkorff/website_backups/leaveroomfordessert`.
