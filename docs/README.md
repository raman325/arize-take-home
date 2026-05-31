# `docs/` — GitHub Pages source

This folder is the source for the deliverable site. It's served at `https://raman325.github.io/<repo-name>/` once GitHub Pages is enabled.

## How to deploy

1. **Push the repo to GitHub** (public — Pages requires it on the Free plan):
   ```bash
   gh repo create arize-take-home --public --source=. --push
   ```
2. **Enable Pages** in the new repo:
   - Settings → Pages
   - Source: `Deploy from a branch`
   - Branch: `main` · folder: `/docs`
   - Save
3. After a minute or two, the site is live at `https://raman325.github.io/arize-take-home/`.

## Local preview

No build step required. Open `docs/index.html` directly in a browser, or serve the folder over HTTP so relative paths to `../README.md` etc. resolve:

```bash
python3 -m http.server --directory docs 8000
# then open http://localhost:8000
```

(Relative links to `../NOTES.md`, `../README.md`, and `../transcripts/...` work on GitHub Pages because the deployed root is the `docs/` folder — those parent-relative links resolve through the repo's URL space when served from GitHub.)

## Editing

The site is a single file: `docs/index.html`. Tailwind CDN + Google Fonts via `<link>` tags. No build, no node_modules.

## Files

- `index.html` — the proposal site (single page, sticky TOC sidebar)
- `screenshots/` — image assets the site references
- `README.md` — this file
