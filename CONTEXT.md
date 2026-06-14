# Options Trade Journal — Project Context

## What We're Building

A SaaS web app for options traders to track trades, P&L, fees, and strategy performance.
Target user: active retail options traders (credit spreads, butterflies, iron condors, CSPs).
Monetization: $15–25/month subscription via Stripe.
Initial data source: thinkorswim (TOS/Schwab) Account Statement CSV export.
Future integrations: Tastytrade API (OAuth, live sync), IBKR Client Portal API.

---

## Current Status

### ✅ DONE: TOS CSV Parser (`tos_parser.py`)

The core parser is complete and validated against a real TOS Account Statement export.

**Architecture decision:** Cash Balance section is the PRIMARY data source (not Account Trade
History). Every trade event flows through Cash Balance with correct signed amounts and fees.
Account Trade History is SECONDARY — used only for individual leg detail and strategy
classification.

**Why Cash Balance is primary:**
- AMOUNT column is already correctly signed (+ = received, - = paid) — no sign inference needed
- Fees (Misc + Commissions) are explicit per transaction
- Covers ALL event types: TRD (opens/closes), RAD (expirations/assignments)
- Description field is structured and parseable
- REF# uniquely identifies each order

**Parser output — `ParseResult` contains:**
- `cash_events: list[CashEvent]` — every TRD/RAD row parsed
- `trades: list[Trade]`         — stitched trade lifecycle objects

**`Trade` fields:**
```python
id: str                          # UUID
underlying: str                  # "SPY", "NVDA", etc.
strategy: StrategyType           # VERTICAL_CALL, BUTTERFLY_PUT, SINGLE_PUT, etc.
spread_label: str                # raw label from TOS description ("VERTICAL", "BUTTERFLY", etc.)
open_events: list[CashEvent]     # TRD rows that opened this trade
close_events: list[CashEvent]    # TRD/RAD rows that closed it
legs: list[TradeLeg]             # individual leg detail from Account Trade History
open_time: datetime
close_time: datetime
expiration: date
is_closed: bool
is_expired: bool                 # True if closed via RAD (expired worthless)
open_amount: float               # net cash at open (+ = credit received, - = debit paid)
close_amount: float              # net cash at close
total_fees: float                # sum of all Misc Fees + Commissions across all events
realized_pnl: float              # open_amount + close_amount (gross, before fees)
realized_pnl_net: float          # realized_pnl - total_fees
notes: str
```

**Strategy types detected:**
`SINGLE_CALL`, `SINGLE_PUT`, `VERTICAL_CALL`, `VERTICAL_PUT`, `BUTTERFLY_CALL`,
`BUTTERFLY_PUT`, `IRON_CONDOR`, `IRON_BUTTERFLY`, `STRADDLE`, `STRANGLE`,
`CALENDAR`, `DIAGONAL`, `COVERED_CALL`, `STOCK`, `UNKNOWN`

**Key parsing behaviors:**
- Split fills (same REF#, multiple cash rows) are deduplicated and amounts accumulated
- Position direction tracking: SELL→BUY = close, BUY→SELL = close, same direction = new open
- RAD rows (expired worthless) matched by underlying + expiration + strike proximity
- Unmatched closes (position opened before export date range) logged as warnings, not fabricated
- Fees tracked separately from P&L so net P&L = gross P&L - fees

**Validated against real account data (5/15/26–6/13/26):**
- 34 cash events → 18 trades (13 closed, 5 open, 1 expired)
- Verified P&L matches TOS: UAL +$80, IONQ +$62, CRM +$105, SNOW +$38, MU +$31
- Total fees $76.41 across all trades

**Known parser limitations / future work:**
- Positions opened before the export date range show as unmatched RAD warnings (expected)
- Assignment handling parses correctly but untested against real assignment data
- Futures options not tested (equity options only in sample data)
- Roll detection not yet implemented (close + same-day reopen on same underlying = roll chain)

---

## TOS Export Instructions (for users)

In thinkorswim desktop:
1. Monitor tab → Account Statement
2. Set desired date range
3. Hamburger icon (top right of panel) → Export to File → save as CSV

The export contains multiple sections. The parser handles:
- `Cash Balance` — primary source
- `Account Trade History` — secondary (leg detail)

Do NOT use Activity & Positions export — different format, won't parse.

---

## Repo Structure (target)

```
options-journal/
├── CONTEXT.md                  ← this file
├── backend/
│   ├── main.py                 ← FastAPI app entry point
│   ├── parser/
│   │   └── tos_parser.py       ← TOS CSV parser (DONE)
│   ├── models/
│   │   ├── db.py               ← SQLAlchemy models
│   │   └── schemas.py          ← Pydantic schemas
│   ├── routers/
│   │   ├── imports.py          ← POST /import/tos
│   │   ├── trades.py           ← GET /trades, GET /trades/{id}
│   │   └── analytics.py        ← GET /analytics/summary, etc.
│   ├── services/
│   │   └── trade_service.py    ← upsert logic, roll detection
│   └── requirements.txt
├── frontend/
│   ├── app/                    ← Next.js 14 app router
│   │   ├── page.tsx            ← dashboard
│   │   ├── trades/
│   │   │   └── page.tsx        ← trade log
│   │   └── import/
│   │       └── page.tsx        ← CSV upload page
│   ├── components/
│   │   ├── TradeTable.tsx
│   │   ├── PnLSummary.tsx
│   │   ├── StrategyBreakdown.tsx
│   │   └── UploadDropzone.tsx
│   └── package.json
└── docker-compose.yml          ← local dev: postgres + backend + frontend
```

---

## Tech Stack Decisions

| Layer | Choice | Reason |
|---|---|---|
| Backend | FastAPI (Python) | Parser is Python; async; clean OpenAPI docs |
| Database | PostgreSQL via Supabase | Free tier; built-in auth; easy to migrate off |
| ORM | SQLAlchemy 2.0 + Alembic | Standard, migrations built in |
| Frontend | Next.js 14 (App Router) | Fast to build; good for dashboards |
| Styling | Tailwind CSS + shadcn/ui | Rapid UI development |
| Auth | Supabase Auth | JWT; row-level security; free tier |
| Payments | Stripe | Subscriptions; webhook-driven entitlement |
| Hosting | Vercel (frontend) + Railway or Fly.io (backend) | Zero-config deploys |
| Local dev | Docker Compose | Consistent Postgres across machines |

---

## Database Schema (target — not yet built)

### `users`
Managed by Supabase Auth. We extend with a `profiles` table.

### `profiles`
```sql
id          uuid PRIMARY KEY REFERENCES auth.users(id)
created_at  timestamptz DEFAULT now()
stripe_customer_id  text
subscription_status text    -- 'active', 'trialing', 'canceled', etc.
subscription_tier   text    -- 'free', 'pro'
```

### `imports`
```sql
id          uuid PRIMARY KEY DEFAULT gen_random_uuid()
user_id     uuid REFERENCES profiles(id)
imported_at timestamptz DEFAULT now()
source      text    -- 'TOS', 'TASTYTRADE', 'IBKR'
filename    text
date_from   date
date_to     date
raw_events  int     -- count of cash events parsed
trades_created int
trades_updated int
```

### `trades`
```sql
id              uuid PRIMARY KEY DEFAULT gen_random_uuid()
user_id         uuid REFERENCES profiles(id)
import_id       uuid REFERENCES imports(id)
underlying      text NOT NULL
strategy        text NOT NULL       -- StrategyType enum value
spread_label    text                -- raw TOS label
open_time       timestamptz
close_time      timestamptz
expiration      date
is_closed       boolean DEFAULT false
is_expired      boolean DEFAULT false
open_amount     numeric(10,2)       -- net cash at open
close_amount    numeric(10,2)       -- net cash at close
total_fees      numeric(10,2)
realized_pnl    numeric(10,2)       -- gross
realized_pnl_net numeric(10,2)      -- net of fees
iv_rank_at_entry numeric(5,2)       -- manually entered or API-sourced later
dte_at_entry    int                 -- days to expiration at open
notes           text
created_at      timestamptz DEFAULT now()
updated_at      timestamptz DEFAULT now()

-- Dedup key: same user + same open_time + same underlying = same trade
UNIQUE (user_id, underlying, open_time)
```

### `cash_events`
```sql
id              uuid PRIMARY KEY DEFAULT gen_random_uuid()
trade_id        uuid REFERENCES trades(id)
user_id         uuid REFERENCES profiles(id)
ref             text                -- TOS REF# (order ID)
event_date      date
event_time      text
event_type      text                -- OPEN, CLOSE, EXPIRATION, ASSIGNMENT
description     text                -- raw TOS description
direction       text                -- BUY or SELL
qty             int
strategy_label  text
expiration      date
strikes         numeric[]           -- array of strikes
option_type     text                -- CALL or PUT
net_price       numeric(10,4)
amount          numeric(10,2)       -- net cash impact
misc_fees       numeric(10,2)
commissions     numeric(10,2)
```

### `trade_legs`
```sql
id              uuid PRIMARY KEY DEFAULT gen_random_uuid()
trade_id        uuid REFERENCES trades(id)
user_id         uuid REFERENCES profiles(id)
side            text                -- BUY or SELL
qty             int
pos_effect      text                -- TO OPEN or TO CLOSE
expiration      date
strike          numeric(10,2)
option_type     text
price           numeric(10,4)
```

### `roll_chains`
```sql
id              uuid PRIMARY KEY DEFAULT gen_random_uuid()
user_id         uuid REFERENCES profiles(id)
trades          uuid[]              -- ordered list of trade IDs in the roll chain
total_pnl_net   numeric(10,2)       -- aggregate P&L across entire roll
created_at      timestamptz DEFAULT now()
```

---

## API Endpoints (target — not yet built)

### Import
```
POST /api/import/tos
  Content-Type: multipart/form-data
  Body: file (CSV)
  Returns: ImportResult { import_id, trades_created, trades_updated, warnings[] }
```

### Trades
```
GET  /api/trades                    list with filters: underlying, strategy, status, date range
GET  /api/trades/{id}               full detail with legs and cash events
PUT  /api/trades/{id}/notes         update notes
GET  /api/trades/{id}/roll-chain    get roll chain if trade is part of one
```

### Analytics
```
GET  /api/analytics/summary         total P&L, win rate, avg winner/loser, total fees
GET  /api/analytics/by-strategy     P&L and win rate broken down by strategy type
GET  /api/analytics/by-underlying   P&L and win rate by underlying
GET  /api/analytics/by-dte          P&L bucketed by DTE at entry
GET  /api/analytics/fees            fee breakdown over time
```

### Webhooks
```
POST /api/webhooks/stripe           handle subscription events
```

---

## Frontend Pages (target — not yet built)

### Dashboard (`/`)
- Total P&L card (gross + net, current period)
- Win rate card
- Total fees card (with % of gross P&L context)
- Open positions table
- Recent closed trades
- P&L over time chart (recharts LineChart)
- Strategy breakdown donut chart

### Trade Log (`/trades`)
- Filterable/sortable table: underlying, strategy, open date, exp, open$, close$, fees, P&L net, status
- Click row → trade detail drawer
- Trade detail: all cash events, leg breakdown, notes field

### Import (`/import`)
- Drag-and-drop CSV upload zone
- Parse preview (shows trade count, date range, warnings) before confirming
- Import history log

### Analytics (`/analytics`)
- P&L by strategy bar chart
- P&L by underlying
- Win rate trends
- Fee drag analysis (fees as % of gross P&L over time)

---

## Immediate Next Steps (in order)

### Step 1 — Project scaffold
```bash
mkdir backend frontend
cd backend && python -m venv venv
pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary python-multipart pydantic supabase
cd ../frontend && npx create-next-app@latest . --typescript --tailwind --app
```

### Step 2 — Docker Compose for local Postgres
```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: options_journal
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

### Step 3 — Alembic migrations
Run `alembic init alembic`, create initial migration for all tables above.

### Step 4 — FastAPI app skeleton
`backend/main.py` with CORS, health check, router includes.

### Step 5 — `POST /api/import/tos` endpoint
- Accept multipart CSV upload
- Run `TOSParser().parse(content)`
- Upsert trades to DB (dedup on `user_id + underlying + open_time`)
- Return summary

### Step 6 — `GET /api/trades` + `GET /api/analytics/summary`
Enough to power the dashboard and trade log.

### Step 7 — Next.js frontend
Dashboard + trade log + import page. No auth yet — hardcode a dev user.

### Step 8 — Supabase Auth
Swap hardcoded user for real JWT auth. Enable RLS on all tables.

### Step 9 — Stripe
Add subscription check middleware. Free tier = last 30 days only. Pro = full history.

### Step 10 — Tastytrade API integration
OAuth flow, live position sync, Greeks at fill auto-populated.

---

## Future Features (backlog)

- **Roll chain detection** — close + same-day reopen on same underlying = roll; link as chain with aggregate P&L
- **IV rank at entry** — pull from Tastytrade API (for TT users) or prompt manual entry at import
- **DTE at entry** — auto-calculate from open_time and expiration, already available
- **Max profit / max loss** — calculate from strikes and premium for defined-risk strategies
- **P&L as % of max profit** — key metric for premium sellers
- **Email digest** — weekly P&L summary email
- **IBKR integration** — Client Portal Web API (REST), lower priority than Tastytrade
- **Mobile-responsive UI** — traders check P&L on phone
- **CSV export** — export filtered trade log to CSV
- **Tax year reporting** — P&L summary by tax year for Schedule D

---

## Key Technical Gotchas to Remember

### Parser
- Cash Balance AMOUNT already net of fees — do not subtract fees from AMOUNT
- Split fills share same REF# — accumulate, don't double-count
- RAD rows have $0 amount — expired worthless P&L = open_amount only
- Position opened before export date range = unmatched RAD warning (not a bug)
- Same underlying, different expiration/strikes = separate independent positions

### FastAPI
- Use `python-multipart` for file upload (`pip install python-multipart`)
- File upload: `file: UploadFile = File(...)` in route signature
- Read bytes: `content = await file.read()`

### Supabase / Postgres
- Enable Row Level Security on all tables: `user_id = auth.uid()`
- `numeric[]` for strikes array in cash_events
- Upsert dedup key: `(user_id, underlying, open_time)` — same trade imported twice = update not insert

### Next.js
- Use App Router (not Pages Router)
- API calls to FastAPI backend via env var `NEXT_PUBLIC_API_URL`
- Supabase client: `@supabase/supabase-js` + `@supabase/auth-helpers-nextjs`

---

## Environment Variables Needed

```bash
# backend/.env
DATABASE_URL=postgresql://dev:dev@localhost:5432/options_journal
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=xxxx
STRIPE_SECRET_KEY=sk_test_xxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxx

# frontend/.env.local
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=xxxx
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Pricing Model

| Tier | Price | Features |
|---|---|---|
| Free | $0 | Last 30 days, manual import only, basic P&L |
| Pro | $19/month | Full history, all analytics, CSV export, priority support |
| (Future) Team | $49/month | Multiple accounts, shared dashboard |

---

## Competitive Landscape

- **tastytrade built-in** — basic, no cross-broker, no analytics depth
- **TradeLog** — desktop app, old UX, no web
- **OptionStrat** — focuses on visualization, not journaling
- **Options Profit Calculator** — pre-trade, not post-trade journaling
- **Spreadsheet** — what most traders use; this replaces it

Our edge: built by an options trader, correct P&L including fees, multi-broker eventually,
clean web UI, affordable.
