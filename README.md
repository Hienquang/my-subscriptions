# Due

A small web app for tracking subscriptions and recurring bills — what you pay
for, from which account, and when it's next due.

Live at **https://hienquang.github.io/my-subscriptions/**

## Shape of the thing

| File | What it is |
| --- | --- |
| `index.html` | The whole app — markup, styles and logic in one file, no build step |
| `supabase.js` | Self-hosted `@supabase/supabase-js` UMD bundle (version in its banner) — as a CDN script its no-cors response could never be cached, which broke offline cold starts |
| `sw.js` | Service worker: caches the shell so it opens with no network |
| `manifest.json` | Makes it installable to a home screen |
| `db/migrations/` | Schema history for the Supabase backend |
| `tests/` | Playwright tests against a stubbed Supabase — see `tests/README.md` |

One file is a deliberate choice, not an accident: it deploys by uploading a
single file, it self-updates by fetching itself, and there is nothing to build.
Worth revisiting past ~1,500 lines.

## Backend

Supabase project `finance-tracker` (`anpvflizwcmyefbxsfpx`), free tier.

- `subscriptions` — one row per bill. `account_id` → `accounts(id)`,
  `cycle_unit`/`cycle_count` for the billing cycle, `due_day` as the month
  anchor, `deleted_at` for soft delete.
- `accounts` — bank accounts and cards. Never deleted, only deactivated.
- `payments` — what was actually paid, when. Planned amount lives on the
  subscription; this is the record of reality.
- `last_payments` — view returning one row per subscription.
- `record_payment()` — logs a payment and advances the due date in one
  transaction.

Row-level security on everything (`user_id = auth.uid()`). Auth is email +
password, with a magic link as the forgotten-password path.

`subscriptions.payment_method` is deprecated — a pre-v5.7 text copy of the
account name, kept read-only as a fallback. Safe to drop once v6.x has been
running a while.

## Working on it

```bash
python3 tests/run_tests.py     # 175 checks; run before committing
python3 tests/shot.py          # screenshots at phone and desktop widths
```

Two conventions worth keeping:

1. **Bump `APP_VERSION`** on every change. It is the only place the version is
   written — the footer label and the self-update check both read it. The app
   fetches itself on open, compares, and reloads once if it's behind.
2. **Add a regression test with every bug fix.** `tests/` exists because v5.4
   and v5.5 were both regressions.

Schema changes go in `db/migrations/` *and* get applied to Supabase, or the two
drift apart.

## Deploying

GitHub Pages from `main` (repo `Hienquang/my-subscriptions`). Push, wait for the
Pages action. If a deploy sticks or reports "Deployment failed, try again later",
push a fresh commit rather than re-running the stuck job — re-running rarely
clears it.

Anyone with the app open picks up the new version on their next launch, without
reinstalling.
