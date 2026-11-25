# DESIGN.md — FactoryFlow "Pouch & Process"

Design direction C. All decisions here map to code in `frontend/`.

---

## 1. Palette

Tokens live in `frontend/tailwind.config.js` → `theme.extend.colors`.

| Token | Hex | Use |
|---|---|---|
| **turmeric-500** | `#E8A317` | Primary accent, welcome strip, BOM highlights |
| turmeric-700 | `#9A6608` | Focus rings, process-line lit connectors |
| turmeric-50/100 | | Hover states, selected product card |
| **chilli-500** | `#C8361D` | Flagged variance bars, error banners, rejected/cancelled status |
| chilli-700 | `#962613` | Flagged variance text |
| **leaf-500** | `#2F6B3A` | Within-tolerance bars, OK status pills (synced/dispatched) |
| leaf-700 | `#22502B` | Tolerance text |
| **choc-900** | `#3B2416` | Headings, button primary, sticky order bar, cost breakdown dark card |
| choc-700/500/300/100 | | Body text scale, borders, greyed items |
| **cream** `#FFF6E3` | | Salesman layout background, process line strip |
| **paper** `#FFFDF8` | | Admin / auditor layout background, card backgrounds |
| **line** `#EADFCB` | | Borders, ruled separators, empty bar backgrounds |

**Rule:** no raw hex in JSX. Every colour reference goes through a Tailwind class.

---

## 2. Typography

| Role | Family | Weight | Tailwind class |
|---|---|---|---|
| Display headings (h1–h2, cost figure, order-bar count) | Bricolage Grotesque | 800 extrabold | `font-display font-extrabold` |
| Sub-headings, card titles, button labels | Bricolage Grotesque | 600 semibold | `font-display font-semibold` |
| Body (all running text, labels, table cells) | Hind Madurai | 400 regular | `font-sans` (default) |
| Emphasis (amounts, pill text, bold labels) | Hind Madurai | 500/600 medium/semibold | `font-medium` / `font-semibold` |
| Numbers (all money and quantities) | Hind Madurai + `.num` utility | — | tabular-nums, lining figures |

Fonts are self-hosted via `@fontsource/bricolage-grotesque` and `@fontsource/hind-madurai` (OFL-1.1).
No Google Fonts CDN in production.

---

## 3. Layout per role

### Salesman (mobile-first, max-w-lg)
Background: `bg-cream`. Full-bleed turmeric welcome strip with kolam dot-grid overlay and a slow-spinning murukku (24 s, `motion-safe` only). Sticky `OrderBar` at the bottom within thumb reach. Product grid: 2 columns on mobile, each `ProductCard` with the item illustration, name, price+GST% label, −/count/+ step buttons and a +10 shortcut. Customer selector: radio-chip buttons (44 px min-height). `Timeline` shows the 4-step progress rail per order.

### Admin / billing desk (max-w-5xl)
Background: `bg-paper`. Order cards with `Pill` status badge, `ItemArt` per line, action buttons in a flex-wrap row. Invoice persistence via `memory.js` so dispatch and payment survive a reload. Part-payment input (w-40) beside the full invoice amount placeholder.

### Production floor (max-w-5xl)
Background: `bg-paper`. `ProcessLine` across the top (4 stations, SVG connector pipes, dashes + `animate-flow` only while DRAFT). Below: `VarianceBars` card (pale plan bar + solid actual bar in leaf or chilli) paired with the `Overheads and cost` card (`CostBreakdown` stacked bar + cost/margin dark panel). `QtyTable` for raw and packaging with `ItemArt` and editable inputs. `PurchaseCard` alongside.

### Stock & reports (max-w-5xl, auditor/owner)
Background: `bg-paper`. Date pickers + Refresh. `Stock summary` table: `ItemArt` + item code, unit in kg/l/pcs, quantities as numbers, closing value in ₹. All numeric columns right-aligned with `.num`. Download buttons per report type (CSV / XLSX). Read-only subtitle ("Every figure is read from the stock ledger…").

---

## 4. Illustrations (`frontend/src/components/SnackArt.jsx`)

All are inline SVGs (aria-hidden; accessible text on the parent). No raster images.

| Artwork | Triggered by code/name containing |
|---|---|
| **Murukku** | `murukku`, `fg`, `finished` — a spiral of half-circle arcs with dashed ridges |
| **Mixture** | `mix`, `mixture` |
| **Chips** | `chip`, `wafer` |
| **Sweet** | `sweet`, `halwa`, `laddu` |
| **Flour sack** | `flour`, `maida`, `wheat` |
| **Oil bottle** | `oil`, `ghee`, `fat` |
| **Spice jar** | `spice`, `masala`, `salt`, `pepper` |
| **Pouch (zigzag seal)** | `pouch`, `pack`, `bag` |
| **Carton box** | `carton`, `box`, `ctn` |
| **Sack fallback** | everything else |

`Logo` exports a compact murukku spiral used in the header and login page.

Rule: `artFor()` matches on lowercased `code` then `name`; it is not exported (lint: fast-refresh). `ItemArt` passes `aria-hidden` and accepts any `className` for sizing.

---

## 5. Motion

All animation is state-driven, not decorative:

| Animation | Trigger | CSS |
|---|---|---|
| `animate-spin-slow` (24 s) | murukku in the welcome banner | `motion-safe:animate-spin-slow` |
| `animate-flow` (pipe dashes) | run status = DRAFT (batch is in the kadai) | removed when COMPLETED |
| `animate-pop` (scale 1→1.18→1) | packet count in `OrderBar` changes | `key={packets}` forces remount |
| `animate-fade-in` (200 ms) | `Banner` component appears | always |
| `transition-[width]` (500 ms) | variance bar widths on data load | CSS transition |

**Rule:** every animation is wrapped in `motion-safe:` or placed inside a CSS block guarded by `@media (prefers-reduced-motion: no-preference)`. The `index.css` prefers-reduced-motion block hard-resets `animation-duration` to 0.01ms and `transition-duration` to 0.01ms for all elements.

---

## 6. Accessibility

- All interactive elements ≥ 44 px in the smallest dimension (`min-h-[44px]`).
- `:focus-visible` outline: 2 px turmeric-700, offset 2 px (no outline on mouse clicks).
- `role="radiogroup"` + `role="radio"` + `aria-checked` on the customer selector.
- `aria-label` on every numeric input (e.g. `"Issued OIL (l)"`).
- `aria-label="Run progress"` on the `ProcessLine` `<ol>`.
- `aria-label={Status: ${step}}` on the order `Timeline` `<ol>`.
- `role="status"` on `Banner` so screen readers announce updates.
- SVG illustrations are `aria-hidden="true"`.
- `<caption>` on `QtyTable` for the screen reader table summary.
- Colour is never the only signal: flagged variance shows "Flagged" text in addition to chilli colour.

---

## 7. Component inventory

| Component | File | Purpose |
|---|---|---|
| `Button` | `ui.jsx` | primary / accent (turmeric) / ghost / danger; min-h 44px, rounded-full |
| `Card` | `ui.jsx` | rounded-2xl, border-line, bg-paper; optional `title` and `actions` slot |
| `Banner` | `ui.jsx` | error / success / info; `role="status"`, `animate-fade-in` |
| `Field` | `ui.jsx` | label + input wrapper |
| `Pill` | `ui.jsx` | wait (turmeric) / ok (leaf) / bad (chilli) / muted (choc) |
| `input` (string export) | `ui.jsx` | shared Tailwind class string for all `<input>` / `<select>` |
| `ItemArt` | `SnackArt.jsx` | aria-hidden SVG illustration keyed to item code/name |
| `Logo` | `SnackArt.jsx` | compact murukku SVG for header + login |
| `Layout` | `Layout.jsx` | sticky header, role nav pills, max-w per role |
| `ProcessLine` | `RunVisuals.jsx` | 4-station progress bar driven by run.status |
| `VarianceBars` | `RunVisuals.jsx` | planned vs actual bars with flagging |
| `CostBreakdown` | `RunVisuals.jsx` | stacked bar + cost/margin dark panel |
| `PurchaseCard` | `PurchaseCard.jsx` | purchase entry for the production user |

---

## 8. Known gaps / next-pass candidates

- **Single-product grid:** if the price list has only one product, the 2-column grid looks sparse. Consider `grid-cols-1` when `products.length === 1`.
- **Disabled button contrast:** the ghost `Add overheads` button when both inputs are empty has low contrast (opacity-50 on a paper background). Already ≥ 3:1 in WCAG AA for large text, but worth revisiting.
- **Admin payment input width:** `!w-40` is a fixed override. On narrow viewports (< 400 px) the flex row wraps correctly, but the input label is not shown until focus — consider a floating `aria-label` tooltip.
- **Owner dashboard:** the `owner` role has no dedicated page yet (they land on stock). P10 will add the dashboard.
- **Invoice reload from another browser:** when an invoice is raised in one browser and dispatch is needed from another, the page shows a message but no action. A `GET /invoices?order_id=` filter endpoint would remove this gap.
- **Service-worker PWA shell:** the offline queue works (localStorage + Idempotency-Key), but the app shell itself is not cached, so a cold offline load shows a blank page.
