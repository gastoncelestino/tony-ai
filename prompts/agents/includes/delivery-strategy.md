### Delivery Strategy

This is collected by `SDD Session Preflight` as the chained PR strategy. If missing, enforce the hard gate before any phase work. Ask which delivery/review strategy they want:

- **`ask-on-risk`** (default): Ask later if `sdd-tasks` forecasts high risk or >400 changed lines.
- **`auto-chain`**: If forecast is high, continue with chained/stacked PR slices without asking again.
- **`single-pr`**: Prefer one PR; if forecast exceeds 400 lines, require `size:exception` before apply.
- **`exception-ok`**: Allow a large PR because the maintainer explicitly accepts `size:exception`.

Cache the delivery strategy for the session. Pass it as `delivery_strategy` to `sdd-tasks` and `sdd-apply` prompts.