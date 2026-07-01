# Theme & Design-System Reference

Everything visual in this template is driven by CSS variables ("tokens") defined in
`app/globals.css`. Pages never hard-code colours — they use tokens, so light/dark mode
and rebranding work everywhere automatically.

A live version of this reference is in the app itself: **Tools → Components**.

---

## Colour tokens

Defined twice: in `:root` (light) and `.dark` (dark).

| Token | Purpose | Light | Dark |
|---|---|---|---|
| `--bg` | Page background | `#f4f4f7` | `#0c0c12` |
| `--surface` | Cards, header, modals | `#ffffff` | `#15151e` |
| `--surface-2` | Inputs, nested surfaces | `#f8f8fb` | `#1b1b26` |
| `--border` | All borders | `#e7e7ef` | `#272733` |
| `--text` | Primary text | `#15131f` | `#ececf2` |
| `--muted` | Secondary text | `#6b6880` | `#a4a2b5` |
| `--faint` | Tertiary text, placeholders | `#9a97ad` | `#6d6b80` |
| `--accent` | Brand colour — buttons, active tabs, links | `#6d28d9` | `#a78bfa` |
| `--accent-2` | Gradient partner for accent | `#9333ea` | `#c084fc` |
| `--accent-soft` | Selected-card background | `#f0ecff` | `#221b3a` |

**To rebrand:** change the three accent values in both blocks. Keep the dark-mode
accent *lighter* than the light-mode one (dark backgrounds need brighter colours
for contrast).

---

## Utility classes (use these in JSX)

| Class | What it does |
|---|---|
| `surface` | Background = card colour |
| `surface-2` | Background = input/nested colour |
| `bd` | Border colour token (combine with Tailwind `border`, `border-t`, …) |
| `txt` | Primary text colour |
| `txt-muted` | Secondary text colour |
| `txt-faint` | Tertiary text colour |
| `accent` | Accent text colour |
| `ctl` | Complete input/chip/secondary-button surface (bg + border + radius) |
| `seg` | Selectable segment card (2px border, 14px radius) |
| `seg-on` | Selected state for `seg` (accent border + soft background) |
| `font-display` | Sora heading font with tight letter-spacing |

For anything not covered, use inline `style={{ color: 'var(--accent)' }}` or
Tailwind arbitrary values like `focus:border-[var(--accent)]`.

---

## Common patterns

### Card
```tsx
<div className="surface bd rounded-2xl border p-6">…</div>
```

### Primary button
```tsx
<button className="rounded-lg px-5 py-2.5 text-sm font-semibold text-white hover:opacity-90"
        style={{ background: 'var(--accent)' }}>
  Submit
</button>
```

### Secondary button / input / chip
```tsx
<button className="ctl px-5 py-2.5 text-sm font-semibold hover:opacity-80">Cancel</button>
<input className="ctl w-full px-3.5 py-2.5 text-sm outline-none focus:border-[var(--accent)]" />
```

### Selectable option card
```tsx
<button className={cn('seg p-4', selected && 'seg-on')}>…</button>
```

### Accent badge
```tsx
<span className="rounded-full px-3 py-1 text-[12px] font-semibold"
      style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
  New
</span>
```

### Gradient CTA button (hero actions, Generate)
```tsx
<button className="flex items-center gap-3 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600
                   px-8 py-4 text-base font-semibold text-white shadow-lg shadow-violet-500/40
                   transition-all hover:shadow-xl hover:scale-105">
  <Zap className="h-5 w-5" /> Generate
</button>
```

### Launcher tile (gradient icon square)
```tsx
<Link className="surface bd rounded-2xl border p-[18px] transition-all hover:-translate-y-0.5
                 hover:shadow-[0_16px_30px_-16px_rgba(50,30,90,0.35)]" href="…">
  <div className="mb-3.5 flex h-[46px] w-[46px] items-center justify-center rounded-[14px]
                  bg-gradient-to-br from-violet-600 to-indigo-600">
    <SomeIcon className="h-[22px] w-[22px] text-white" />
  </div>
  <div className="txt text-[13.5px] font-semibold">Feature name</div>
  <div className="txt-faint text-[11.5px]">Short subtitle</div>
</Link>
```

### Toggle switch
```tsx
<button onClick={toggle}
        className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
        style={{ background: on ? 'var(--accent)' : 'var(--border)' }}>
  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform
                    ${on ? 'translate-x-6' : 'translate-x-1'}`} />
</button>
```

### Hero banner (dashboard top)
```tsx
<section className="relative overflow-hidden rounded-3xl
                    bg-gradient-to-br from-[#2a1d4d] via-[#6d28d9] to-[#9333ea] px-8 py-9 text-white">
  <div aria-hidden className="pointer-events-none absolute -right-16 -top-20 h-72 w-72 rounded-full bg-pink-500/40 blur-3xl" />
  <div aria-hidden className="pointer-events-none absolute left-[28%] -bottom-28 h-64 w-64 rounded-full bg-sky-400/30 blur-3xl" />
  {/* content */}
</section>
```

### Icon gradient pairs (launcher tiles / thumbnails)
Assign one gradient per feature/content type in your project and use it consistently.

| Gradient | Classes |
|---|---|
| Violet | `from-violet-600 to-indigo-600` |
| Sky | `from-sky-500 to-blue-600` |
| Pink | `from-pink-500 to-rose-500` |
| Amber | `from-amber-500 to-orange-500` |
| Emerald | `from-emerald-500 to-green-600` |

---

## Typography

- **Body:** Inter (`--font-sans`) — applied to `body` automatically.
- **Headings / brand:** Sora via the `font-display` class — opt-in, use on `h1`/`h2` and stat numbers.
- Both are loaded with `next/font` in `app/layout.tsx` (no layout shift, self-hosted).

Sizing conventions used across the template:
page title `text-[22px] font-extrabold`, card title `text-lg font-bold`,
body `text-sm`, labels `text-[13px] font-semibold`, hints `text-xs`.

---

## Dark mode — how it works

1. `context/ThemeContext.tsx` exports `themeInitScript`, injected in `app/layout.tsx`'s
   `<head>`. It runs **before paint** and sets the `.dark` class from localStorage
   (or the OS preference) — so there is no flash of the wrong theme.
2. `ThemeProvider` + `useTheme()` manage the state; `ThemeToggle` is the button.
3. Because every colour is a token, `.dark` swaps all of them at once. If you only
   use the token classes above, your pages support dark mode with **zero extra work**.

The only special-case rule: `.dark .ctl` makes inputs slightly lighter than cards
so empty fields are visibly different from the card behind them.

---

## Layout structure

```
app/layout.tsx          ← fonts, ThemeProvider, toaster (root, applies to everything)
app/(app)/layout.tsx    ← app shell: full-height column, scrolling <main>, footer
app/(app)/*/page.tsx    ← each page renders <Header /> + <PageHeader /> itself
```

The header is sticky *inside* the scrolling main area — that's why each page renders
`<Header />` at the top rather than the layout doing it. Follow the page recipe in
[README.md](./README.md) and this just works.
