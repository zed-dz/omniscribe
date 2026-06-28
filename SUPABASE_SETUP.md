# Connect OmniScribe Cloud to Supabase (free tier)

The cloud app (`api/index.py`) already contains the integration (`omniscribe/store.py`).
It **activates automatically** once two environment variables are present — no code changes.
Without them, the app still works (assets are returned inline as downloads).

When connected, each generation:
- saves a **history row** to a `dissections` table, and
- uploads each asset to **Supabase Storage**, returning persistent public URLs.

## 1. Create a free Supabase project
Go to <https://supabase.com> → New project (free tier). Note your **Project URL**
(`https://xxxx.supabase.co`) and, under *Project Settings → API*, the **service_role** key.

## 2. Create the table (SQL Editor → run this)
```sql
create table if not exists dissections (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  title text,
  language text,
  provider text,
  input_chars int,
  assets jsonb
);
-- allow the service key full access (service_role bypasses RLS by default; this is optional)
alter table dissections enable row level security;
```

## 3. Create a public Storage bucket
Storage → New bucket → name it **`assets`** → toggle **Public**.

## 4. Add the env vars to Vercel
From the project folder, run:
```bash
vercel env add SUPABASE_URL production          # paste https://xxxx.supabase.co
vercel env add SUPABASE_SERVICE_KEY production   # paste the service_role key
vercel env add SUPABASE_BUCKET production        # type: assets
vercel deploy --prod                             # redeploy to pick them up
```
(or add them in the Vercel dashboard → Settings → Environment Variables, then redeploy.)

## Done
The capabilities banner will show "Results are saved to your database", asset cards will link
to persistent Supabase Storage URLs, and every run is logged in the `dissections` table.

> Security note: the **service_role** key is powerful — it's only ever used server-side in the
> Vercel function and is never exposed to the browser. Keep it secret (do not commit it).
