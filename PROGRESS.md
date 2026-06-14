# Project Scaffold Progress Log

## Completed - 2025-06-13

### 1. Project Structure Created
```
tos_options_journal/
├── backend/
│   ├── .env                    # Supabase + DB credentials
│   ├── .gitignore
│   ├── requirements.txt
│   ├── config.py               # Pydantic settings
│   ├── database.py             # SQLAlchemy session management
│   ├── main.py                 # FastAPI app entry point
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 001_initial_schema.py
│   │       └── 002_row_level_security.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── db.py               # SQLAlchemy models (secure schema)
│   │   └── schemas.py          # Pydantic schemas
│   ├── parser/
│   │   ├── __init__.py
│   │   └── tos_parser.py       # TOS CSV parser
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── imports.py          # POST /api/import/tos
│   │   ├── trades.py           # GET /api/trades
│   │   └── analytics.py        # GET /api/analytics/summary
│   └── services/
│       ├── __init__.py
│       └── trade_service.py    # Business logic
├── frontend/
│   ├── .env.local              # Supabase public keys
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx        # Dashboard
│   │   │   ├── trades/
│   │   │   │   └── page.tsx    # Trade log
│   │   │   └── import/
│   │   │       └── page.tsx    # CSV import
│   │   ├── components/
│   │   │   ├── PnLCard.tsx
│   │   │   ├── TradeTable.tsx
│   │   │   └── UploadDropzone.tsx
│   │   └── lib/
│   │       ├── api.ts          # Backend API client
│   │       └── supabase.ts     # Supabase client
├── docker-compose.yml          # Optional local Postgres
└── context.md                  # Project context doc
```

### 2. Secure Database Schema

**Security architecture implemented:**

- `profiles` table: Links to Supabase `auth.users`, contains per-user `salt` and computed `data_key` (SHA-256 hash)
- `billing` table: Separated from profiles for Stripe data isolation
- `trades`, `cash_events`, `trade_legs` tables: Use `owner_key` (hash) instead of direct FK to users
  - If these tables are compromised, attacker cannot link back to users without also having `profiles` table AND the salt

**Row Level Security (RLS):**
- All tables have RLS enabled
- `profiles`, `billing`, `imports`: Direct `auth.uid()` check
- `trades`, `cash_events`, `trade_legs`: Subquery lookup via `data_key`

### 3. Environment Files Created

**backend/.env:**
- DATABASE_URL (Supabase Postgres)
- SUPABASE_URL
- SUPABASE_SERVICE_KEY
- STRIPE_SECRET_KEY (placeholder)
- STRIPE_WEBHOOK_SECRET (placeholder)

**frontend/.env.local:**
- NEXT_PUBLIC_SUPABASE_URL
- NEXT_PUBLIC_SUPABASE_ANON_KEY
- NEXT_PUBLIC_API_URL

### 4. Backend Implementation

- FastAPI app with CORS, health check, and router structure
- SQLAlchemy 2.0 models with type hints
- Alembic migrations (initial schema + RLS)
- TOS CSV parser (ported from context)
- Trade service with import/upsert logic
- Pydantic schemas for API validation

### 5. Frontend Implementation

- Next.js 14 (App Router) with TypeScript + Tailwind
- Dashboard page with P&L summary cards
- Trade log page with filtering and pagination
- Import page with drag-and-drop CSV upload
- Supabase client setup

---

## Next Steps

1. **Run migrations:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   alembic upgrade head
   ```

2. **Start backend:**
   ```bash
   uvicorn main:app --reload
   ```

3. **Start frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

4. **Create a test user in Supabase** (via dashboard or Auth API)

5. **Wire up auth** - Add JWT validation to FastAPI endpoints

6. **Test import** - Upload a TOS CSV and verify parsing
