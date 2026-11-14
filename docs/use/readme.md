# Using Sola

## Launch the prototype

From the project directory run `npm run dev`, then visit **http://127.0.0.1:239**. No login, backend or API key is needed. The date, persona and calendar are sample data.

## Everyday walkthrough

1. **Overview:** see a sample day, household tasks and a friendly check-in. Choose a mood to open a scripted conversation.
2. **Groceries:** mark bought items, add your own item, or filter essentials. A new item has an unknown price; it is not silently priced at zero in the displayed estimate.
3. **Compare:** “One easy stop” uses Demo Market prices. “Lowest item total” chooses the lower fictional price per item across two fictional stores. Travel and delivery are excluded.
4. **Review:** inspect remaining items, subtotal and sample time. Save the demo plan; no money is spent and no calendar is changed.
5. **Print:** use the browser print dialog to create a paper list or PDF. Bought items are excluded from the printed list.
6. **Laundry:** review the sample wardrobe and proposed slot. Saving changes only local browser state.
7. **Discover:** save sample weekend ideas. These are not real listings.
8. **Talk to Sola:** send a message or use a suggestion. Replies are scripted; they do not understand arbitrary requests or search the web.
9. **Wellbeing:** try a local check-in. No contact, GPS, authentication or emergency service is connected.
10. **Preferences:** use the sidebar Settings control or avatar. Memory consent is a local preference only; reset restores demo fixtures.

## Judge demo: prototype versus live submission

The current frontend is a UI demo and does **not** yet meet the challenge requirement for live Exa queries. Say that clearly when showing it. The intended live demo after backend implementation:

- Start with confirmed low-stock breakfast items and a real user budget/location.
- Submit a fresh query, including a judge-chosen variation.
- Show Researcher progress, Exa-derived pages, excerpts and retrieval times.
- Open the exact evidence for a product price and explain any unknowns.
- Compare equivalent products, demonstrate a one-store preference and modify the budget.
- Review a revised immutable plan and approve saving/exporting it.
- Finish with an actionable shopping list and retailer links, without claiming a purchase.

Fallback if a retailer blocks extraction: show the partial result, source failure and manual link. A clearly explained partial result is more credible than a fabricated price. Never present recorded fixtures as a live response.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Port 239 occupied | Set `$env:PORT=240`, then rerun `npm run dev` |
| Blank page from disk | Use the local HTTP URL; modules do not run reliably from `file://` |
| Custom item has no estimate | Expected: it needs live research or a manual price |
| Demo changes disappear | Browser storage may be blocked/private; changes still work during the session |
| Want original fixtures | Settings → Reset demo data |
| Fonts look different offline | Expected: optional web fonts fall back to installed sans-serif |

## Prototype limitations

The browser contains only fictional data and ordinary local storage, not secure personal-data storage. No background reminders run after closing the page. Check-in flags do not model daily recurrence. Purchases, reservations, location sharing, social posting, medical tasks and emergency actions are unavailable.
