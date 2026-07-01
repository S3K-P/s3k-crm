# S3K UI Starter

A ready-to-use **Next.js app template** with the S3K AI Studio look: light + dark theme,
top-tab navigation, ⌘K quick search, and a consistent design system driven by CSS tokens.

Start any new project with this and you get the same structure, theme, and colours —
then rebrand it for your project by editing **two files** (see below).

![Stack](https://img.shields.io/badge/Next.js%2016-React%2019-blue) ![Style](https://img.shields.io/badge/Tailwind%20CSS-tokens-purple)

---

## Quick start

```bash
npm install
npm run dev        # → http://localhost:3000
```

That's it. You'll see a working app with a Dashboard (hero banner + launcher tiles +
recent work), a Sample Tool (the full 3-pane generation-form layout), a Components
reference page, and Settings — all using the shared theme.

---

## How to adapt this template for YOUR project

You only need to touch **two files** to make it yours:

### 1. `config/site.ts` — brand + navigation (start here)

Everything about *what the app is called* and *what pages it has* lives in this one file:

- `BRAND` — logo mark, product name, tagline, footer line
- `TABS` — the top-level tabs in the header
- `SUBNAV` — the second-row links under each tab
- `SEARCH_ITEMS` — entries in the ⌘K quick-search

Rename the tabs, add your own pages under `app/(app)/your-page/page.tsx`,
and point the nav at them. The header updates automatically.

### 2. `app/globals.css` — colours (rebrand here)

All colours are CSS variables at the top of this file (`:root` for light, `.dark` for dark).
Change `--accent` / `--accent-2` / `--accent-soft` to your project's brand colour and the
buttons, active tabs, links, and selected cards all follow. No other file needs touching.

> Fonts: the template uses **Inter** (body) and **Sora** (headings), loaded in
> `app/layout.tsx`. Swap them there if your project uses different fonts.

---

## Building new pages — the recipe

There are two page layouts. Both start with `<Header />` at the top.

**Tool page (3-pane: Sources rail | form | Recent rail)** — copy
`app/(app)/tools/sample-form/page.tsx`. It contains every form pattern:
numbered card sections, selectable cards with check marks, dropdown with live
guide, slider, 2K/4K pickers, toggle switches, the accent Content-Brief panel
with quality meter, and the gradient CTA button.

```tsx
'use client';
import Header from '@/components/Header';
import PageHeader from '@/components/PageHeader';
import ToolWorkspace from '@/components/workspace/ToolWorkspace';
import { SomeIcon } from 'lucide-react';

export default function MyToolPage() {
  return (
    <div className="flex h-full flex-col">
      <Header />
      <ToolWorkspace>   {/* add hideSources to drop the left rail */}
        <PageHeader icon={SomeIcon} title="My Tool" subtitle="What it does" />
        <div className="p-8">
          <div className="max-w-5xl mx-auto space-y-8">
            <div className="surface bd rounded-2xl border p-6 shadow-sm">
              {/* numbered section */}
            </div>
          </div>
        </div>
      </ToolWorkspace>
    </div>
  );
}
```

**Full-width page (dashboard style)** — copy `app/(app)/dashboard/page.tsx`.
It has the hero gradient banner with glow orbs, launcher tiles with gradient
icon squares, the "At a glance" stat list, and "Recent work" thumbnail cards.

The side rails (`components/workspace/SourcesRail.tsx` and `RecentRail.tsx`)
ship with static demo data — swap in your own API calls where marked.

Then register the page in `config/site.ts` (SUBNAV + SEARCH_ITEMS) so it appears
in the navigation and ⌘K search.

**Golden rule: never hard-code colours.** Use the token classes
(`surface`, `bd`, `txt`, `txt-muted`, `ctl`, `seg`, …) or `var(--accent)`.
That's what keeps dark mode and rebranding working for free.
See [THEME.md](./THEME.md) for the full token reference.

---

## What's included

| Piece | File(s) |
|---|---|
| Colour tokens (light + dark) | `app/globals.css` |
| Brand + navigation config | `config/site.ts` |
| Top-tab header with sub-nav + ⌘K search | `components/Header.tsx` |
| Dark/light toggle (no flash on load) | `context/ThemeContext.tsx`, `components/ThemeToggle.tsx` |
| Page title banner | `components/PageHeader.tsx` |
| 3-pane tool layout (Sources / form / Recent rails) | `components/workspace/` |
| Footer | `components/Footer.tsx` |
| App shell (scrolling main + footer) | `app/(app)/layout.tsx` |
| Fonts (Inter + Sora) + toasts (sonner) | `app/layout.tsx` |
| `cn()` class helper | `lib/utils.ts` |
| Example pages | `app/(app)/dashboard`, `tools/sample-form`, `tools/components`, `settings` |

Dependencies are minimal on purpose: Next.js, React, Tailwind, lucide-react (icons),
sonner (toasts), clsx + tailwind-merge (the `cn()` helper).

---

## Sharing this template with the team

Recommended setup (one-time, by whoever owns the repo):

1. Push this folder to GitHub as a new repository (e.g. `s3k-ui-starter`).
2. In the repo: **Settings → General → check "Template repository"**.
3. Team members click **"Use this template" → "Create a new repository"** on GitHub —
   they get a fresh copy with clean history, ready to rename and build on.

Alternatively (no GitHub template): clone and re-init —

```bash
git clone <repo-url> my-new-project
cd my-new-project
rm -rf .git && git init
npm install
```

---

## Checklist for a new project

- [ ] `npm install && npm run dev` — confirm it runs
- [ ] Edit `config/site.ts` — brand name, mark, tagline, footer
- [ ] Edit `config/site.ts` — replace TABS / SUBNAV / SEARCH_ITEMS with your pages
- [ ] Edit `app/globals.css` — set your accent colours (light + dark)
- [ ] Update `name` in `package.json` and the title in `app/layout.tsx` metadata
- [ ] Delete the example pages you don't need (keep `tools/components` as a style reference while developing)
- [ ] Build pages using the recipe above — tokens only, no hard-coded colours
