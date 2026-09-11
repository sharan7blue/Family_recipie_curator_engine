# PrepLink — System Architecture

**Last updated:** 2026-09
**Status:** Phase 0–1 architecture. Phase 2+ extensions noted inline.

> **Note (2026-09-11):** This document supersedes ADR-002's Celery + Redis
> worker fleet. See [[ADR-004-drop-celery-worker-fleet]] for the rationale.
> The backend described below runs the AI pipeline synchronously in-process;
> there is no task queue or separate worker fleet.

---

## 1. System overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Client layer (Next.js 15, Edge runtime)                            │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────────┐  │
│  │ /recipe/[id] │  │ / (home)       │  │ /nutrition/[nutrient]  │  │
│  │ RSC + ISR    │  │ client shell   │  │ RSC + ISR              │  │
│  └──────────────┘  └────────────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
              │ HTTPS                         │ HTTPS
              ▼                               ▼
┌─────────────────────────────┐   ┌──────────────────────────────┐
│  FastAPI backend (Python)   │   │  Supabase (PostgreSQL + Auth) │
│  Port 8000                  │   │  Row Level Security           │
│  ┌───────────────────────┐  │   │  ┌────────────────────────┐  │
│  │ AI Pipeline           │  │   │  │ recipes                │  │
│  │  1. Platform detect   │  │   │  │ household_profiles     │  │
│  │  2. Transcript / OCR  │  │   │  │ cart_sessions          │  │
│  │  3. LLM extraction    │  │   │  │ creator_attributions   │  │
│  │  4. Nutrition score   │  │   │  └────────────────────────┘  │
│  │  5. Age adapt         │  │   └──────────────────────────────┘
│  │  6. Pantry filter     │  │
│  │  7. Cart assembly     │  │   ┌──────────────────────────────┐
│  └───────────────────────┘  │   │  USDA FoodData Central API   │
│  ┌───────────────────────┐  │   │  (nutrition lookup)           │
│  │ API Waterfall         │  │   └──────────────────────────────┘
│  │  Claude → OpenAI →    │  │
│  │  Gemini + hibernation │  │   ┌──────────────────────────────┐
│  └───────────────────────┘  │   │  YouTube Data API v3          │
└─────────────────────────────┘   │  (metadata, captions)         │
                                  └──────────────────────────────┘
```

---

## 2. Frontend architecture

### 2.1 Next.js 15 App Router conventions

```
frontend/src/
├── app/
│   ├── layout.tsx              # Root layout, metadata, global CSS
│   ├── page.tsx               # Homepage — "use client" shell
│   ├── recipe/
│   │   └── [id]/
│   │       └── page.tsx       # RSC — fetches recipe, injects JSON-LD
│   ├── nutrition/
│   │   └── [nutrient]/
│   │       └── page.tsx       # RSC hub page
│   ├── for/
│   │   └── [audience]/
│   │       └── page.tsx       # RSC audience hub
│   └── sitemap.ts             # Dynamic sitemap
├── components/
│   ├── cart/
│   │   ├── MobilePreCartView.tsx    # RSC — layout, image, trust banner
│   │   ├── CartInteractiveShell.tsx # "use client" — checkbox state
│   │   ├── CheckboxItem.tsx         # "use client" leaf
│   │   ├── PantryAccordion.tsx      # "use client" leaf
│   │   └── StickyCartFooter.tsx     # "use client" leaf
│   ├── seo/
│   │   └── RecipeStructuredData.tsx # RSC — JSON-LD injection
│   └── ui/
│       ├── ProcessingState.tsx      # "use client" — stage animation
│       └── WarningBanner.tsx        # RSC — static warning
├── hooks/
│   ├── useRecipeParse.ts       # Cart build state machine
│   └── useCartState.ts         # Per-item checked state + overrides
├── lib/
│   ├── api.ts                  # Typed fetch wrappers to FastAPI
│   └── instacart.ts            # Cart URL builder + routeToInstacart()
└── types/
    ├── recipe.ts               # Mirrors backend/schemas/recipe.py
    └── clinical.ts             # Mirrors backend/schemas/clinical.py
```

### 2.2 RSC boundary placement

The RSC/client split is the most important architectural decision in the
frontend. The rule: RSC by default, `"use client"` only at leaf nodes that
own interactive state.

```
MobilePreCartView (RSC)
├── Hero <Image> (RSC — Next.js Image component)
├── ClinicalTrustBanner (RSC — static markup)
└── CartInteractiveShell ("use client" — owns all checkbox state)
    ├── CheckboxItem ("use client" — individual toggle)
    ├── PantryAccordion ("use client" — open/close state)
    └── StickyCartFooter ("use client" — live count + CTA)
```

**Why this matters:** RSC renders on the server and streams to the client.
`"use client"` components ship JavaScript to the browser. The smaller the
client boundary, the faster the page is interactive.

### 2.3 Data flow

```
URL submitted (user)
    │
    ▼
useRecipeParse hook (client)
    │ POST /api/v1/recipe/parse
    ▼
FastAPI pipeline (server)
    │ returns RecipeParseResponse
    ▼
CartInteractiveShell (client)
    │ useState for checked/unchecked
    ▼
StickyCartFooter (client)
    │ derives itemCount from state
    ▼
routeToInstacart() (client)
    │ builds URL, opens new tab
    ▼
Instacart (external)
```

---

## 3. Backend architecture

### 3.1 FastAPI application structure

```
backend/
├── main.py                     # App factory, middleware, router registration
├── core/
│   ├── config.py              # Pydantic Settings — all env vars
│   └── logger.py              # Structured logging
├── routers/
│   ├── recipe.py              # /recipe/parse, /recipe/{id}, /recipe/history
│   ├── household.py           # /household CRUD
│   └── instacart.py           # /cart/link, /retailers
├── schemas/
│   ├── recipe.py              # Master data contracts (Pydantic v2)
│   └── clinical.py            # ClinicallySafeRecipe + CartPayload
└── services/
    ├── ai_pipeline.py         # Base 6-stage extraction pipeline
    ├── clinical_pipeline.py   # Clinical extension + infographic hook
    ├── api_waterfall.py       # Claude → OpenAI → Gemini with hibernation
    └── nutrition_engine.py    # USDA FoodData Central integration (Phase 0)
```

### 3.2 AI pipeline (7 stages)

```python
Stage 1: _detect_platform(url) → platform: str
    # "youtube" | "instagram" | "tiktok" | "twitter" | "web"

Stage 2a: extract_youtube_transcript(url) → (text, method)
    # youtube-transcript-api → full text
    # Fallback: extract_via_gemini() → Gemini 1.5 Pro vision

Stage 2b: extract_via_gemini(url, platform) → text
    # OG image + title + description → recipe text

Stage 3: call_clinical_extraction(system, user) → dict
    # API Waterfall: Claude → OpenAI → Gemini
    # response_format=json_object, seed=42, temperature=0.1
    # Pydantic validation of output

Stage 4: _build_parsed_ingredient(raw, pantry_items) → ParsedIngredient
    # Pantry confidence: LLM suggestion + deterministic table
    # User pantry override → VERY_HIGH confidence

Stage 5: _apply_age_adaptations(ingredients, age_groups) → list
    # Deterministic rules: TODDLER_FORBIDDEN, SENIOR_ADAPTATIONS
    # No LLM in this stage — all rule-based

Stage 6: score_nutrition(ingredients, age_group) → NutritionSummary
    # USDA FoodData Central lookup per ingredient
    # DRI coverage by age group

Stage 7: build_instacart_cart(recipe) → InstacartCart
    # Filter: pantry_skip_by_default = True → excluded
    # instacart_query optimised at extraction time
```

### 3.3 API Waterfall — rate limit resilience

Three-tier waterfall with header-parsed hibernation. Never blocks the
asyncio event loop.

```python
WATERFALL_ORDER = [
    (ModelTier.CLAUDE,  _call_claude),   # Primary: highest clinical accuracy
    (ModelTier.OPENAI,  _call_openai),   # Secondary: structured output
    (ModelTier.GEMINI,  _call_gemini),   # Tertiary: generous rate limits
]

# On full exhaustion:
reset_timestamp = _parse_reset_timestamp(response.headers)
sleep_secs = reset_timestamp - time.time() + HIBERNATION_BUFFER_SECS
await asyncio.sleep(sleep_secs)  # Non-blocking
# Job requeued before sleeping
```

Header formats handled:
- Anthropic: `x-ratelimit-reset-requests` (ISO-8601)
- OpenAI: `x-ratelimit-reset-requests` (seconds with "s" suffix)
- Gemini: `retry-after` (integer seconds)

---

## 4. Database schema

Full schema in `supabase_schema.sql`. Key tables:

### recipes
```sql
CREATE TABLE recipes (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id           TEXT,                    -- nullable (anonymous recipes)
  source_url        TEXT NOT NULL,
  source_platform   TEXT NOT NULL,
  title             TEXT NOT NULL,
  slug              TEXT UNIQUE,             -- SEO slug
  ingredients       JSONB NOT NULL,          -- ParsedIngredient[]
  steps             JSONB NOT NULL,          -- CookingStep[]
  nutrition         JSONB NOT NULL,          -- NutritionSummary
  primary_age_group TEXT NOT NULL,
  all_age_groups    TEXT[] NOT NULL,
  confidence_score  NUMERIC(3,2) NOT NULL,
  extraction_method TEXT NOT NULL,
  is_public         BOOLEAN DEFAULT true,    -- public = indexable
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- GIN index for ingredient search
CREATE INDEX idx_recipes_ingredients_gin ON recipes USING GIN (ingredients);
-- For SEO hub pages
CREATE INDEX idx_recipes_age_group ON recipes(primary_age_group, created_at DESC);
CREATE INDEX idx_recipes_public ON recipes(is_public, created_at DESC) WHERE is_public = true;
```

### nutrition_scores
```sql
-- Separate table for nutrition scoring — allows re-scoring without touching recipes
CREATE TABLE nutrition_scores (
  recipe_id         UUID REFERENCES recipes(id) ON DELETE CASCADE,
  age_group         TEXT NOT NULL,
  iron_pct          NUMERIC(5,2),   -- % of DRI covered
  calcium_pct       NUMERIC(5,2),
  vitamin_d_pct     NUMERIC(5,2),
  fiber_pct         NUMERIC(5,2),
  absorption_flags  TEXT[],         -- ["vitamin_c_iron_boost", "calcium_iron_inhibit"]
  nutrition_brief   TEXT,           -- Generated brief text (paid feature)
  scored_at         TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (recipe_id, age_group)
);
```

### creator_attributions
```sql
CREATE TABLE creator_attributions (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  handle        TEXT NOT NULL UNIQUE,    -- YouTube @handle
  youtube_url   TEXT,
  revenue_share NUMERIC(3,2) DEFAULT 0.01, -- 1% of cart value
  total_carts   INTEGER DEFAULT 0,
  total_revenue NUMERIC(10,2) DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 5. Nutrition engine (Phase 0 build)

### USDA FoodData Central integration

```python
# services/nutrition_engine.py

USDA_API_BASE = "https://api.nal.usda.gov/fdc/v1"
USDA_API_KEY  = settings.USDA_API_KEY  # Free, register at api.nal.usda.gov

async def lookup_nutrients(
    canonical_name: str,
    quantity: float,
    unit: str,
    age_group: AgeGroup,
) -> dict[str, float]:
    """
    Returns {iron_mg, calcium_mg, vitamin_d_iu, fiber_g} for given
    ingredient + quantity.
    Caches results in Redis (or Supabase if Redis not yet provisioned).
    """
    cache_key = f"nutrients:{canonical_name}:{quantity}:{unit}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Search FoodData Central
    search_resp = await httpx.get(
        f"{USDA_API_BASE}/foods/search",
        params={"query": canonical_name, "api_key": USDA_API_KEY, "pageSize": 1}
    )
    fdc_id = search_resp.json()["foods"][0]["fdcId"]

    # Get full nutrient data
    food_resp = await httpx.get(
        f"{USDA_API_BASE}/food/{fdc_id}",
        params={"api_key": USDA_API_KEY}
    )
    nutrients = extract_priority_nutrients(food_resp.json(), quantity, unit)

    await cache.set(cache_key, nutrients, ttl=86400)
    return nutrients


DRI_TARGETS = {
    AgeGroup.TODDLER: {
        "iron_mg": 7.0,
        "calcium_mg": 700.0,
        "vitamin_d_iu": 600.0,
        "fiber_g": 19.0,
    },
    AgeGroup.CHILD: {
        "iron_mg": 10.0,
        "calcium_mg": 1000.0,
        "vitamin_d_iu": 600.0,
        "fiber_g": 25.0,
    },
    AgeGroup.ADULT: {
        "iron_mg": 18.0,
        "calcium_mg": 1000.0,
        "vitamin_d_iu": 600.0,
        "fiber_g": 25.0,
    },
    AgeGroup.SENIOR: {
        "iron_mg": 8.0,
        "calcium_mg": 1200.0,
        "vitamin_d_iu": 800.0,
        "fiber_g": 21.0,
    },
}
```

### Absorption interaction rules (deterministic)

```python
ABSORPTION_INTERACTIONS = [
    {
        "name": "vitamin_c_iron_boost",
        "trigger_a": ["red pepper", "lemon", "orange", "tomato", "strawberry",
                      "broccoli", "kale"],
        "trigger_b": ["spinach", "lentil", "bean", "tofu", "beef", "chicken"],
        "message": "Vitamin C source boosts iron absorption — good pairing.",
        "direction": "positive",
    },
    {
        "name": "calcium_iron_inhibit",
        "trigger_a": ["milk", "cheese", "yogurt", "dairy"],
        "trigger_b": ["spinach", "lentil", "bean", "tofu"],
        "message": "Calcium may reduce iron absorption. Consider eating these at separate meals.",
        "direction": "caution",
    },
]
```

---

## 6. Infrastructure and deployment

### Phase 0–1 (lean, low cost)

| Service | Purpose | Cost |
|---|---|---|
| Vercel | Next.js hosting, Edge functions, ISR | $20/mo (Pro) |
| Railway or Fly.io | FastAPI backend (1 instance) | $10–20/mo |
| Supabase | PostgreSQL + Auth + Storage | $25/mo (Pro) |
| Upstash Redis | Nutrition lookup cache | $10/mo |
| Anthropic API | Primary LLM | Usage-based |
| OpenAI API | Secondary LLM | Usage-based |
| Google AI | Gemini + YouTube API | Usage-based |
| USDA FoodData | Nutrition data | Free |
| **Total** | | **~$65–80/mo fixed** |

### Phase 2+ additions

| Service | Purpose | Cost |
|---|---|---|
| Vercel Analytics | Real-user performance | Included in Pro |
| Sentry | Error tracking | $26/mo |
| PostHog | Product analytics | $0 (free tier to 1M events) |
| Resend | Transactional email | $20/mo |

### Environment variables (complete list)

```bash
# AI providers
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...

# Data
USDA_API_KEY=...              # Register free at api.nal.usda.gov
SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...      # Frontend use only

# Monetisation
INSTACART_AFFILIATE_TAG=preplink
INSTACART_PARTNER_ID=...      # From IDP approval

# App
APP_URL=https://preplink.app
NEXT_PUBLIC_API_URL=https://api.preplink.app/api/v1
NEXT_PUBLIC_INSTACART_AFFILIATE_TAG=preplink

# Cache
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=...

# Security
INTERNAL_API_KEY=...          # Backend-to-backend
ENV=production
```

---

## 7. Error handling and observability

### Error classification

| Error type | Handling | User sees |
|---|---|---|
| URL not a YouTube Short | Return 400, no retry | "This URL doesn't look like a YouTube video" |
| Transcript unavailable | Fallback to Gemini | Confidence score adjusted, amber banner |
| LLM rate limit | Waterfall to next provider | No user impact |
| All LLMs exhausted | Hibernate, requeue | "Processing — we'll notify you when ready" |
| USDA API down | Serve recipe without nutrition score | No nutrition brief shown |
| Instacart API error | Log, return cart URL manually | Cart still builds, affiliate tracking lost |
| Pydantic validation failure | Log schema violation, return 422 | "Something went wrong — try again" |

### Logging structure (all logs JSON)

```python
{
  "timestamp": "2026-09-07T12:34:56Z",
  "level": "INFO",
  "service": "ai_pipeline",
  "event": "recipe_processed",
  "recipe_id": "uuid",
  "source_platform": "youtube",
  "extraction_method": "transcript",
  "confidence_score": 0.91,
  "processing_time_ms": 8420,
  "cart_items": 9,
  "pantry_skipped": 3,
  "model_used": "claude"
}
```

---

## 8. Security model

### Authentication flow (Supabase)

```
User → Magic link email → Supabase Auth
Supabase issues JWT → stored in httpOnly cookie
Next.js middleware validates JWT on protected routes
FastAPI validates JWT via Supabase service key
```

### Row Level Security

```sql
-- Users can only read/write their own data
CREATE POLICY "user_isolation" ON household_profiles
  USING (user_id = auth.uid()::TEXT);

-- Recipes: owner or public
CREATE POLICY "recipe_access" ON recipes
  USING (is_public = true OR user_id = auth.uid()::TEXT);

-- Nutrition scores: follow recipe access
CREATE POLICY "nutrition_score_access" ON nutrition_scores
  USING (
    EXISTS (
      SELECT 1 FROM recipes r
      WHERE r.id = nutrition_scores.recipe_id
      AND (r.is_public = true OR r.user_id = auth.uid()::TEXT)
    )
  );
```

### API key handling

- API keys never sent to client
- Instacart affiliate tag sent as query param (acceptable — public affiliate IDs)
- USDA API key backend-only
- All LLM API keys backend-only, never in `NEXT_PUBLIC_*` variables

---

## 9. Testing strategy

### Unit tests (pytest)

```
tests/unit/
├── test_pantry_model.py          # Confidence classification
├── test_age_adaptations.py       # Toddler/senior rule engine
├── test_nutrition_scoring.py     # DRI coverage calculation
├── test_absorption_interactions.py  # Vitamin C + iron pairing
└── test_pydantic_schemas.py      # Schema validation edge cases
```

### Integration tests (pytest + httpx)

```
tests/integration/
├── test_recipe_pipeline.py       # Full pipeline with mocked LLM
└── test_instacart_cart.py        # Cart assembly + URL generation
```

### E2E tests (Playwright — already built)

```
tests/e2e/
└── mobile-pre-cart.spec.ts       # QG1: accordion, count, screenshot
```

### Quality gates before any deploy

1. All unit tests pass
2. All integration tests pass
3. All Playwright E2E tests pass
4. Lighthouse mobile ≥ 95
5. No Pydantic validation warnings in test logs
6. TypeScript `tsc --noEmit` passes with zero errors

---

## 10. Phase 2+ architecture extensions

These are not built yet. Documented here for architectural awareness.

### Multi-retailer support
Add `RetailerAdapter` abstract class. Each retailer (Kroger, Walmart, Amazon
Fresh) implements `build_cart_url(items, retailer_config)`. Existing Instacart
router becomes `InstacartAdapter`. User selects preferred retailer in
household settings.

### Nutrition Intelligence API (B2B)
Separate FastAPI router `/api/b2b/v1/` with API key authentication (not JWT).
Exposes: `POST /extract` (same pipeline), `POST /score` (nutrition scoring
only), `GET /ingredients/{canonical_name}/nutrients`. Rate limited at 1000
calls/day on free tier, unlimited on paid.

### iOS native app (Phase 3)
React Native (Expo) sharing the same TypeScript types and API client.
Core screens only: home (URL input), pre-cart view, household settings.
No feature parity with web — native app is for speed and push notifications.

### CPG brand portal
New Supabase schema: `cpg_placements`, `placement_analytics`. Separate
Next.js admin route group (`/brand/`) with magic-link auth for brand users.
Placement logic: when `nutrition_scores.iron_pct < 30` for toddler household
AND `cpg_placements` has an active iron-category placement, insert sponsored
ingredient into cart with `is_sponsored: true` and disclosure label.
