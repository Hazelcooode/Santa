# Figment — mobile app frontend

A phone-first companion to the Sola website (repo root). It is a separate, dependency-free prototype (`index.html`, `styles.css`, `data.js`, `app.js`) with fictional data. It does not share code with the website. Only the visual language is shared.

## Run

```bash
python3 -m http.server 5180 --directory mobile
```

Open http://127.0.0.1:5180 in a narrow (≈390 px) viewport. State lives in localStorage under `figment-state-v1`. Me → Reset demo data clears it.

## Screens

Home · Today (decorate the tree) · Shopping lists · Laundry plans · Events & travels · ChatWithMe · Health · Safety · Me. Navigation is hash based (`#/today`, `#/shopping`, …).

## Mobile-only feature: decorate today's tree

Today has six daily tasks. Settling a task (the button on its card) hangs one decoration on the tree: star, baubles, candy cane, bell and garland. The daily check-in first asks for a (simulated) fingerprint or Face ID. Progress is stored per day. Finishing all six completes the tree.

## Shared art style with the website

The mobile UI uses the website's design tokens (`src/styles.css`), so the two read as one product:

| Element | Website | Mobile |
| --- | --- | --- |
| Surfaces | paper `#f7f7f3`, cards `#fffefa`, 1px `#e7e8e1` borders | same |
| Accents | lavender `#ece8f7`/`#8b75a9`, peach `#f9e8dc`, sage `#e7eedf`, terracotta `#d6744c` | same, as tinted panels and cards |
| Type | Manrope headings, DM Sans body | same |
| Icons | 24px line icons, 1.6 stroke, round caps, inside pastel 37px tiles | same icon paths (home, groceries, laundry, discover, chat, safety) and the same tiles |
| Buttons | 8px radius, dark `#353b35` primary, white secondary | same |
| Assistant avatar | animated lavender character (two arms, two legs) in the hero, companion card and chat header, from `src/art.js` | the same character stands beside the tree, smaller than it, and appears on the call screen |
| Tree | the hero shows the mobile tree, fully decorated (`src/art.js`) | the tree is decorated one task at a time |

Legacy CSS variable names (`--c-brand`, `--c-card-*`) are kept as aliases onto the website palette, so markup and JS that use them still work.
