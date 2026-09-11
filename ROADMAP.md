# PrepLink — Product Roadmap

**Product:** Nutrition-first family meal intelligence platform
**Model:** Consumer subscription + CPG data + B2B API
**Principle:** The curation engine is the product. The cart is how we monetise it.

---

## North Star metric

**Weekly Nutrition Score (WNS):** % of households meeting ≥3 of 4 priority
nutrients (iron, calcium, vitamin D, fiber) across their PrepLink-sourced meals
in a given week. This is the metric no competitor tracks. When WNS goes up,
retention goes up. When WNS goes up, CPG brands want access to users.

---

## Phase 0 — Foundation (Weeks 1–6)

**Goal:** Prove the extraction-to-cart loop works accurately enough to show people.
**Gate:** 70%+ cart acceptance rate (user does not modify more than 2 items).

### Build
- YouTube Shorts transcript extraction pipeline (youtube-transcript-api)
- Gemini vision fallback for Shorts without captions
- Extraction confidence scorer — surfaces in UI when accuracy may be lower
- Nutrition scoring engine v1: USDA FoodData Central lookup + DRI targets by age
- Age adaptation rule engine (toddler / infant 6–9m / infant 9–12m / senior)
- Pantry probability model (USDA/Nielsen staple frequency table)
- Instacart cart builder + affiliate link generator
- Mobile pre-cart view (MobilePreCartView.tsx — already built)
- Household profile: age group, dietary flags, pantry items
- Basic auth (Supabase email/magic link — no OAuth complexity yet)
- Instrumentation: every URL → cart → click → order event tracked

### Do not build in Phase 0
- Long-form video mode
- Weekly meal planner
- Nutrition dashboard
- CPG placement
- Native app
- Anything requiring a legal review

### Exit criteria
- 50 beta families using the product weekly
- Cart acceptance rate ≥ 70%
- Instacart affiliate link click-through ≥ 40% of cart views
- Zero critical extraction failures (wrong ingredient substituted for safety reason)

---

## Phase 1 — Distribution Engine (Months 2–4)

**Goal:** Engineering as marketing. Make the product shareable by design.
**Gate:** 500 active households, 30-day retention ≥ 45%.

### Build
- Share card generator: auto-generate an OG image for each recipe with
  nutrition badge ("Iron: 38% of toddler daily target") — shareable on
  Instagram/WhatsApp without leaving the app
- Deep link architecture: `preplink.app/r/{recipe_slug}` resolves to the
  pre-cart view, pre-populated with the household profile if logged in
- "Adapted for [Child's name]" personalisation on the share card
- Creator tag system: food creators can embed `?pl=@handle` in their YouTube
  description — PrepLink tracks attribution and surfaces creator stats
- YouTube Shorts "Save to PrepLink" bookmarklet for desktop
- Confidence UI: low-confidence extractions show a "We estimated some
  quantities — tap to review" banner before the cart builds
- Schema.org Recipe + VideoObject JSON-LD injection (see SEO.md)

### Monetisation
- Instacart affiliate live (apply week 1, approve ~week 3)
- Free tier: 5 recipes/week, basic age adaptation, no nutrition data
- Paid tier launches at $9/month: unlimited recipes + nutrition brief per cart
- The nutrition brief is the paid feature: "This meal covers 38% of Lena's
  weekly iron target. The bell pepper boosts absorption — good pairing."

### Distribution tactics
- Submit to r/toddlerparenting, r/babyfood, r/mealplanning — not as an ad,
  as a share card from a real recipe the team used
- Partner with 5 YouTube food creators (under 100k subs — faster to respond)
  who make toddler/family content. Offer free Pro + revenue share from their
  attributed carts
- Submit to ProductHunt in week 8 — share card makes it visual enough to land
  in the top 5 of the day

### Exit criteria
- 500 active households
- 30-day retention ≥ 45%
- 80 paying subscribers ($720 MRR)
- 3 creator partnerships with attributed cart conversions
- Share card CTR > 8% (industry benchmark for food content)

---

## Phase 2 — Product Depth (Months 5–9)

**Goal:** Make cancellation irrational. The weekly meal planner and nutrition
tracker create a habit loop that makes the $9/month feel like a bargain.
**Gate:** $8,000 MRR, 12-week retention ≥ 55%.

### Build
- Long-form YouTube mode: chapter extraction, full ingredient list with steps,
  timestamp links back to the original video
- Weekly meal planner: drag 5 recipes into a week view, auto-merge into a
  single Instacart cart with deduplication
- Nutrition gap tracker: weekly dashboard showing iron/calcium/vitamin D/fiber
  coverage by day — gaps shown in amber, targets met in green
- Family profile upgrade: multiple children with different age groups, each
  with their own DRI targets
- Recipe save + history: 30-recipe history, saved collections by goal
  ("High-iron dinners", "Finger foods Lena likes")
- Confidence scoring v2: flag individual ingredients with low confidence,
  let user correct them — corrections feed back to improve the model
- Meal planner weekly email: "Your plan for next week" — sent Sunday, links
  to the merged Instacart cart

### Monetisation
- $9/mo plan: nutrition brief + unlimited recipes
- $14/mo plan: adds weekly meal planner, nutrition gap tracker, multi-child
- First CPG research pilot: approach 1 brand (Danone, Kraft Heinz, or an
  organic baby food brand) with a 90-day pilot proposal — $3,000–5,000 flat
  fee. They get: product appears in relevant cart builds when user's nutrition
  gap matches, plus an anonymised report of cart acceptance rate by age group.
  Fully disclosed in UI.

### Exit criteria
- $8,000 MRR (400 paying subscribers mixed across both tiers)
- 12-week retention ≥ 55%
- 1 CPG pilot signed ($3,000–5,000 one-time)
- Nutrition gap tracker weekly active rate ≥ 60% of Pro subscribers

---

## Phase 3 — Revenue Architecture (Months 10–18)

**Goal:** Stack the three revenue rails so no single one is load-bearing.
**Gate:** $25,000 MRR, B2B API pilot live with 1 external client.

### Build
- Multi-retailer cart: Kroger, Walmart, Amazon Fresh alongside Instacart —
  user picks preferred retailer in household settings
- CPG brand portal v1: self-serve dashboard where a brand can set a placement
  budget, pick target nutrition gaps, and see their cart acceptance rate in
  real time
- Nutrition Intelligence API v1: same engine that powers the consumer product,
  exposed as a REST API with per-call pricing ($0.04/call or $500/mo flat).
  Target: pediatric meal kit apps, hospital discharge nutrition portals,
  WIC-adjacent platforms
- iOS native app (React Native): offline recipe access, push notification for
  weekly plan reminder, widget showing weekly nutrition score
- Aggregate nutrition trend report v1: anonymised, aggregate data product sold
  to CPG nutrition teams — "What nutrients are parents of toddlers most
  frequently deficient in, by region, by month." No PII. $10,000–25,000/qtr.

### Monetisation
- Consumer subscriptions: $22,000 MRR at 1,800 subscribers
- CPG placement (3 brands at $2,000–4,000/month each): $8,000 MRR
- B2B API (1 external client): $3,000–5,000 MRR
- Affiliate baseline: $2,000–4,000 MRR
- Total target: $35,000–40,000 MRR

### Exit criteria
- $25,000 MRR
- 1 B2B API client live
- 3 CPG brands on placement programme
- Series A conversation ready: 18 months of nutrition data, proven unit
  economics, B2B revenue diversification

---

## Phase 4 — Platform (Months 19–30)

**Goal:** Become the infrastructure layer that other products in the family
nutrition space buy rather than build.

### Build
- Nutrition Intelligence API v2: WebHook support, custom DRI target overrides,
  white-label UI components
- HCP portal: paediatrician-facing nutrition planner — parents share their
  PrepLink nutrition history with their child's doctor
- Multi-language extraction: Spanish-language YouTube content (massive
  underserved segment in US family nutrition)
- Acquisition positioning: data room prepared. Target acquirers: Instacart
  (nutrition intelligence layer), Walmart Health (family nutrition data),
  a large CPG (Nestlé, Danone — access to first-party family nutrition intent
  data is worth 10-100x what a recipe app is worth)

---

## What we explicitly will not build (scope protection)

- A recipe database. We process external content. We do not host it.
- A meal kit delivery service. We route to existing retailers.
- A social network. Share cards are one-directional. No follows, no feeds.
- A medical device or clinical diagnostic tool. Nutrition guidance is
  informational. "Adapted for toddlers" not "clinically prescribed."
- Anything requiring HIPAA compliance in the first 18 months.

---

## Dependency map

```
Phase 0 → Phase 1: Instacart affiliate approval (apply week 1)
Phase 1 → Phase 2: 500 active users for meaningful CPG pilot conversation
Phase 2 → Phase 3: $8k MRR to fund iOS app and API infrastructure
Phase 3 → Phase 4: B2B client + 18mo data asset for acquisition positioning
```

Every phase exit criterion is a real gate, not a calendar date.
