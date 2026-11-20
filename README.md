# Tokensand-Project

Cartwise is a rule-based shopping-agent prototype for finding a storage cart that fits a real space and budget.

## Run

```sh
python3 -m http.server 8765
```

Open http://localhost:8765. No dependencies or API keys required.

## Demo

1. Keep the default $50 budget and 16 × 18 × 28 inch space.
2. Run the comparison: RÅSKOG compact is selected at an estimated $32.69 with 9% tax and $0 fees.
3. Inspect the rejected alternatives and retailer evidence links.
4. Save the purchase checklist, check off actions, open the retailer and download the checklist or audit JSON.
5. Try a $10 budget to see the no-match case.

## Scope and evidence

Four IKEA US product snapshots retrieved November 20, 2026. Sources are linked in `engine.mjs`. The policy selects the lowest estimated total among eligible options, allows 90-degree rotation and adds 0.5 inches clearance per dimension. Tax applies to item price; fees are user supplied. Member promotions are excluded.

This prototype uses deterministic rules, not an LLM or live product search. Prices and availability are not refreshed automatically. It saves a local shopping checklist, not a retailer cart, reservation or order. Storage is browser-local and the exported audit is editable, not tamper-proof. No payment data is collected.

## Validation

Core evaluation checked for default selection, no match, rotated fit and material restrictions. Browser verified recommendation rendering and successful checklist creation.

## Files

- `index.html`: responsive interface
- `app.js`: checklist, local storage, audit and downloads
- `engine.mjs`: sourced catalog and decision policy
