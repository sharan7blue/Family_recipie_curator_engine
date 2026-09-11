# PrepLink — Product Requirements Document

**Version:** 1.0 (Phase 0–1 scope)
**Status:** Active
**Owner:** Founding team
**Last updated:** 2026-09

---

## 1. Problem statement

Parents watching YouTube Shorts food content cannot act on what they see.
The gap between "I just saw a great toddler meal" and "those ingredients are
in my fridge" has no good solution. Existing shoppable recipe tools
(Pinterest/Walmart, Northfork, SideChef) build carts but do not score them
nutritionally. A parent of a toddler does not just want a cart — they want
to know whether the meal is actually good for their child.

**The jobs to be done:**

1. "I saw a Shorts recipe and I want to cook it tonight — build me the cart."
2. "I need to make sure Lena gets enough iron this week — help me plan meals
   that cover her targets."
3. "I'm worried this recipe has too much sodium for a 14-month-old — tell me
   before I buy the ingredients."

No existing product does all three. PrepLink does.

---

## 2. Users

### Primary: Nutrition-anxious parents of children under 5

- Age: 26–38
- Behavior: Watches YouTube Shorts food content 4+ times per week
- Pain: Knows their toddler's diet is probably suboptimal; does not know how
  to fix it without a nutritionist
- Willingness to pay: $8–14/month for confidence that meals are nutritionally
  appropriate
- Platform: 92% mobile

### Secondary: Intentional family meal planners

- Age: 28–42
- Behavior: Plans meals weekly, watches long-form YouTube cooking content,
  already has an Instacart account
- Pain: Meal planning is 45 minutes of manual work; wants automation that
  respects dietary constraints across different family members
- Willingness to pay: $12–16/month for full meal planner with merged cart
- Platform: Split mobile/desktop

### Out of scope (Phase 0–1)

- Single adults without children
- Professional chefs or food creators
- Households without internet access or without an online grocery option
- Non-US/Canada households (Instacart coverage constraint)

---

## 3. Product principles

**Nutrition first, cart second.** The cart is the output. The nutrition
scoring is the reason to use PrepLink over just pasting a URL into Pinterest.
Every product decision runs through this lens: does this make the nutrition
intelligence more useful, or does it distract from it?

**One action per screen.** The mobile-first parent using this while a toddler
is shouting does not read. Every screen has one primary action. Secondary
information is collapsed by default.

**Honesty over polish.** When extraction accuracy is low, say so. When a
recipe has high sodium, flag it. When a pantry item was skipped, explain why.
The parent who trusts PrepLink trusts it because it tells the truth.

**Engineering as distribution.** Every feature either helps the user or helps
a user share the product with another user. Features that do neither are cut.

---

## 4. Feature specifications

### 4.1 YouTube Shorts extraction (P0)

**Input:** Any YouTube Short URL (youtu.be/*, youtube.com/shorts/*)
**Output:** Structured ingredient list with quantities, units, canonical names

**Extraction pipeline:**
1. Detect video ID from URL
2. Attempt `youtube-transcript-api` transcript fetch (languages: en, en-US)
3. If transcript unavailable: Gemini 1.5 Pro vision on OG thumbnail + video
   title + description text
4. Pass raw text to OpenAI GPT-4o with `response_format=json_object`,
   `seed=42`, `temperature=0.1` — forces deterministic structured output
5. Validate against `ParsedIngredient` Pydantic schema
6. Assign confidence score (0.0–1.0) based on extraction method and
   completeness

**Confidence scoring rules:**
- Transcript available + ≥8 ingredients found: 0.85–1.0
- Transcript available + <8 ingredients: 0.65–0.84
- Vision fallback + description keywords: 0.50–0.64
- Vision fallback only: 0.30–0.49

**UI behaviour by confidence:**
- ≥0.75: show cart normally
- 0.50–0.74: show amber banner "Some quantities were estimated — review before
  ordering"
- <0.50: show yellow banner "This recipe was partially extracted — we recommend
  reviewing all quantities"

**Acceptance criteria:**
- [ ] Correctly extracts ≥8 ingredients from a 60-second Short with captions
- [ ] Fallback to Gemini when transcript disabled
- [ ] Confidence score surfaced in UI
- [ ] Processing time <15 seconds P95
- [ ] Graceful error if URL is not a valid YouTube Short

---

### 4.2 Nutrition scoring engine (P0)

**Purpose:** Score every extracted recipe against USDA Dietary Reference
Intake (DRI) targets for the household's age group.

**Priority nutrients (USDA 2025–2030 Dietary Guidelines):**
- Iron (mg) — critical for cognitive development; toddlers chronically low
- Calcium (mg) — bone density; most toddler diets insufficient
- Vitamin D (IU) — immune function; deficiency widespread
- Fiber (g) — gut health; children average 50% of target

**Data source:** USDA FoodData Central API (free, authoritative, updated)

**Scoring logic:**
```
ingredient_nutrients = usda_lookup(canonical_name, quantity, unit)
daily_coverage_pct = ingredient_nutrients[nutrient] / dri_target[age_group][nutrient]
recipe_score[nutrient] = sum(daily_coverage_pct for all ingredients)
```

**DRI targets used (per day):**
```
toddler (1-3yr): iron 7mg, calcium 700mg, vit_d 600IU, fiber 19g
child (4-8yr):   iron 10mg, calcium 1000mg, vit_d 600IU, fiber 25g
adult:           iron 18mg, calcium 1000mg, vit_d 600IU, fiber 25g
senior:          iron 8mg, calcium 1200mg, vit_d 800IU, fiber 21g
```

**Output (nutrition brief — paid feature):**
> "This meal covers 38% of Lena's daily iron target. The red pepper in this
> recipe boosts iron absorption — a smart pairing."

Absorption interaction rules (deterministic, not LLM):
- Vitamin C source present + iron source present → flag as "absorption boost"
- Calcium source + iron source in same meal → flag as "may reduce iron
  absorption — consider spacing these"
- Dairy + iron-rich legumes in same meal → flag

**Acceptance criteria:**
- [ ] USDA FoodData lookup returns data for ≥90% of canonical ingredient names
- [ ] DRI coverage calculated correctly for toddler age group (unit tested)
- [ ] Absorption interaction flags correct for vitamin C + iron pairing
- [ ] Nutrition brief renders in paid UI within 500ms of cart build
- [ ] Nutrient values cached: same ingredient + quantity → no repeat API call

---

### 4.3 Age adaptation rule engine (P0)

**Purpose:** Deterministically modify or flag ingredients based on the
household's age group configuration. Runs before the LLM extraction pass.

**Toddler safety rules (deterministic, sourced from AAP guidelines):**

| Trigger ingredient | Action | Substitute | Reason |
|---|---|---|---|
| honey | substitute | maple syrup | Botulism risk <2yr |
| whole nuts | substitute | finely ground nuts | Choking hazard |
| popcorn | omit | — | Choking hazard |
| raw carrots | substitute | steamed carrots | Choking hazard |
| hot sauce | omit | — | Capsaicin, no nutritional need |
| fish sauce | reduce | 50% of stated amount | Sodium content |
| added salt | reduce | 30% of stated amount | Renal load |
| alcohol | omit | — | Safety |

**UI representation:**
- Items with substitutions show ⚡ badge + note: "Swapped for [substitute] —
  original contains [reason]"
- Omitted items shown as struck-through with reason
- Safety notes visible but not alarming — informational, not medical

**Legal constraint:** All adaptations labelled "adapted for toddlers" not
"clinically safe" or "medically recommended." Disclaimer in footer:
"PrepLink provides nutritional guidance for informational purposes.
Consult your pediatrician for medical advice."

**Acceptance criteria:**
- [ ] Honey correctly substituted to maple syrup for toddler households
- [ ] Omitted items do not appear in Instacart cart
- [ ] Safety note displayed for every adaptation
- [ ] Disclaimer present on every cart view
- [ ] Zero adaptation rules require LLM inference — all deterministic

---

### 4.4 Pantry probability model (P0)

**Purpose:** Prevent cart inflation by skipping items the household very likely
already owns.

**Skip-by-default threshold:** PantryConfidence.VERY_HIGH (≥85% of households)

**Items skipped by default:**
salt, water, black pepper, vegetable oil, cooking spray

**Items offered to skip (HIGH confidence — user toggles):**
olive oil, butter, sugar, flour, garlic powder, onion powder, paprika

**User override:** "Pantry staples" accordion in pre-cart view. Collapsed by
default. User can add any skipped item back to cart with one tap.

**Personal pantry:** Users can declare items they personally own. These are
promoted to VERY_HIGH confidence regardless of table value.

**Acceptance criteria:**
- [ ] Salt and water never appear in default cart
- [ ] Pantry accordion collapsed by default (Playwright test required)
- [ ] User can add any pantry item back in one tap
- [ ] Personal pantry items persist across sessions
- [ ] No item appears in both fresh list and pantry accordion

---

### 4.5 Mobile pre-cart view (P0)

**Purpose:** The screen parents see before they tap "Send to Instacart."
This is the primary UI. Everything else is secondary.

**Layout (mobile-first, max-width 480px):**

```
┌─────────────────────────────┐
│  [Hero image — 4:5 ratio]   │
│  [Recipe title overlay]     │
├─────────────────────────────┤
│  [Nutrition brief — paid]   │  ← amber/green depending on score
├─────────────────────────────┤
│  Fresh to Buy               │
│  ☑ Chicken thighs   800g    │
│  ☑ Coconut milk     1 can   │
│  ☑ Fresh ginger     1.5 tbsp│
│  ...                        │
├─────────────────────────────┤
│  ▼ Pantry staples (3)       │  ← collapsed by default
├─────────────────────────────┤
│  [Share card button]        │
├─────────────────────────────┤
│  ██████ Send 8 items ██████ │  ← sticky, count updates live
└─────────────────────────────┘
```

**Performance requirements (QG2):**
- LCP < 1.2s: hero image uses `<Image priority={true} />`
- TTFB < 200ms: recipe page on edge runtime with 1-hour ISR
- Lighthouse ≥ 95 on mobile

**Accessibility requirements:**
- All checkboxes have native `<input type="checkbox">` with visible label
- Pantry accordion has `aria-expanded` and `aria-controls`
- Sticky footer CTA has `aria-label` with item count
- Clinical trust banner has `role="note"`
- Skip link to main content
- `prefers-reduced-motion` respected on all animations

**Acceptance criteria:**
- [ ] Playwright: accordion collapsed by default
- [ ] Playwright: unchecking item decrements CTA count by 1
- [ ] Playwright: checking pantry item increments CTA count by 1
- [ ] Playwright: screenshot diff < 2% on 390×844 viewport
- [ ] CTA disabled when 0 items selected
- [ ] Lighthouse mobile score ≥ 95

---

### 4.6 Household profile (P0)

**Purpose:** Store the family configuration that personalises every
extraction, nutrition score, and cart.

**Fields:**
```typescript
HouseholdProfile {
  id: uuid
  user_id: string
  nickname: string              // "Our Family"
  age_groups: AgeGroup[]        // ["toddler", "adult"]
  dietary_restrictions: DietaryFlag[]
  pantry_items: string[]        // Personal pantry overrides
  default_servings: number      // 1-12
  zip_code: string | null       // Retailer localisation
  instacart_retailer_id: string | null
}
```

**UX rules:**
- Profile set up on first launch (3-screen onboarding, <60 seconds)
- Multiple profiles supported (for families with children at different stages)
- Profile visible and editable from every screen
- Changing age group triggers re-scoring of saved recipes

**Acceptance criteria:**
- [ ] Onboarding completes in <60 seconds
- [ ] Profile persists across sessions (Supabase RLS)
- [ ] Changing toddler age group removes honey from subsequent carts
- [ ] Multiple household profiles creatable from settings

---

### 4.7 Share card generator (P1)

**Purpose:** Engineering as marketing. Every recipe becomes a shareable asset
that acquires new users.

**Share card format:** 1080×1350 (4:5 Instagram-optimal)

**Content:**
- Recipe thumbnail (or Gemini-generated food image if none available)
- Recipe title
- Nutrition badge: "Iron: 38% of toddler daily target ✓"
- "Adapted for toddlers" tag
- PrepLink wordmark + QR code linking to `preplink.app/r/{slug}`

**Generation:** Server-side via `@vercel/og` (Edge-compatible, no Puppeteer)

**Trigger:** "Share" button on pre-cart view. Web Share API on mobile
(WhatsApp, iMessage, Instagram Stories). Clipboard fallback on desktop.

**Attribution:** Share cards carry `?ref={creator_handle}` when creator-
attributed. Cart conversions attributed back to creator for revenue share.

**Acceptance criteria:**
- [ ] Share card generates in <800ms
- [ ] QR code resolves to correct recipe page
- [ ] Nutrition badge shows correct nutrient and coverage value
- [ ] Web Share API used on mobile; clipboard fallback on desktop
- [ ] `?ref=` attribution tracked and stored per conversion

---

## 5. Non-functional requirements

### Performance
- P95 cart build time: <15 seconds (extraction + nutrition scoring + cart assembly)
- P95 page load (pre-cart view): <1.2 seconds LCP
- API availability: 99.5% uptime (single-region acceptable in Phase 0–1)
- Database query P95: <100ms

### Security
- All user data encrypted at rest (Supabase default AES-256)
- API keys stored in environment variables, never in code
- Supabase Row Level Security enabled on all tables
- No PII in logs
- Instacart affiliate ID not exposed client-side

### Privacy
- No sale of individual user data
- Aggregate nutrition data may be used for product improvement and (with
  disclosure) CPG research — opt-out in settings
- COPPA compliance: no data collection from children. We collect data about
  children's age groups but not from children themselves.
- GDPR-adjacent practices from launch: data export and deletion on request

### Legal
- All nutrition guidance labelled "for informational purposes only"
- "Adapted for [age group]" — never "clinically safe" or "medically recommended"
- CPG placements fully disclosed in UI with "Sponsored" label
- Creator revenue share documented in creator agreement
- Instacart affiliate terms complied with (no artificial click inflation)

---

## 6. Success metrics by phase

| Metric | Phase 0 target | Phase 1 target | Phase 2 target |
|---|---|---|---|
| Active households | 50 | 500 | 2,000 |
| Cart acceptance rate | ≥70% | ≥72% | ≥75% |
| Instacart CTR | ≥40% | ≥42% | ≥45% |
| 30-day retention | — | ≥45% | ≥55% |
| Paying subscribers | 0 | 80 | 400 |
| MRR | $0 | $720 | $8,000 |
| NPS (parent segment) | — | ≥45 | ≥52 |
| Weekly Nutrition Score | Baseline | Baseline + 8% | Baseline + 18% |

---

## 7. Out of scope — permanent

- Hosting recipe content (we process external URLs only)
- Meal kit delivery
- Social features (follows, feeds, comments)
- Medical device classification
- HIPAA compliance
- Non-English language content (Phase 0–2)
- Desktop-first design (mobile is primary)
