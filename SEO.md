# PrepLink — Schema.org Reference

**Purpose:** Every recipe page, hub page, and creator page carries structured
data that enables Google Rich Results (Recipe cards, FAQ panels, Breadcrumbs,
Video search integration).

**Implementation:** All schemas injected by `RecipeStructuredData.tsx` RSC
into `<head>` as `<script type="application/ld+json">`. Zero client JavaScript
required.

---

## 1. Recipe schema (every /recipe/[slug] page)

The core schema that enables Recipe rich results in Google Search.

```json
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Spinach and Lentil Soup — adapted for toddlers",
  "description": "Iron-rich toddler meal from [Creator] — covers 38% of daily iron target for children aged 1–3. Honey-free, low-sodium, and adapted for toddler safety.",
  "image": [
    "https://preplink.app/og/spinach-lentil-soup-toddler-iron.jpg"
  ],
  "author": {
    "@type": "Person",
    "name": "[Creator handle]",
    "url": "https://youtube.com/@{handle}"
  },
  "publisher": {
    "@type": "Organization",
    "name": "PrepLink",
    "url": "https://preplink.app",
    "logo": {
      "@type": "ImageObject",
      "url": "https://preplink.app/logo-schema.png",
      "width": 512,
      "height": 512
    }
  },
  "datePublished": "2026-09-07T00:00:00Z",
  "dateModified": "2026-09-07T00:00:00Z",
  "prepTime": "PT10M",
  "cookTime": "PT25M",
  "totalTime": "PT35M",
  "recipeYield": "4 servings",
  "recipeCategory": "Main Course",
  "recipeCuisine": "International",
  "keywords": "toddler iron recipe, iron-rich toddler food, lentil soup baby, spinach toddler meal",
  "recipeIngredient": [
    "150g red lentils",
    "2 cups baby spinach",
    "1 medium sweet potato, diced",
    "1 red bell pepper, diced",
    "400ml low-sodium vegetable broth",
    "1 tsp ground cumin",
    "1 tsp olive oil"
  ],
  "recipeInstructions": [
    {
      "@type": "HowToStep",
      "position": 1,
      "name": "Prepare vegetables",
      "text": "Dice sweet potato and red bell pepper into small, finger-food-sized pieces suitable for toddlers."
    },
    {
      "@type": "HowToStep",
      "position": 2,
      "name": "Cook lentils",
      "text": "Rinse red lentils and combine with vegetable broth in a medium saucepan. Bring to a boil, then reduce heat and simmer for 15 minutes."
    },
    {
      "@type": "HowToStep",
      "position": 3,
      "name": "Add vegetables",
      "text": "Add sweet potato, bell pepper, and cumin. Simmer for an additional 10 minutes until vegetables are soft."
    },
    {
      "@type": "HowToStep",
      "position": 4,
      "name": "Finish with spinach",
      "text": "Stir in baby spinach and cook for 2 minutes until wilted. The bell pepper vitamin C boosts iron absorption from the spinach and lentils."
    }
  ],
  "nutrition": {
    "@type": "NutritionInformation",
    "servingSize": "1 serving (approx. 220g)",
    "calories": "210 kcal",
    "proteinContent": "12g",
    "carbohydrateContent": "32g",
    "fatContent": "4g",
    "fiberContent": "8g",
    "sodiumContent": "180mg",
    "sugarContent": "6g"
  },
  "suitableForDiet": [
    "https://schema.org/LowSaltDiet",
    "https://schema.org/VegetarianDiet"
  ],
  "video": {
    "@type": "VideoObject",
    "name": "Spinach and Lentil Soup — original recipe by [Creator]",
    "description": "Original cooking video. PrepLink adapted this recipe for toddler safety.",
    "thumbnailUrl": "https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
    "embedUrl": "https://www.youtube.com/embed/{video_id}",
    "contentUrl": "https://www.youtube.com/watch?v={video_id}",
    "uploadDate": "{video_upload_date}",
    "duration": "PT1M23S"
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.7",
    "ratingCount": "23",
    "reviewCount": "23"
  }
}
```

**Notes on field selection:**
- `recipeIngredient`: quantities included for voice search ("how much spinach")
- `recipeInstructions`: `HowToStep` with `position` enables step-by-step
  assistant integration
- `video`: linking to original creator's video is the SEO moat — Recipe +
  VideoObject is a compound signal that generic recipe sites cannot replicate
- `suitableForDiet`: uses Schema.org Diet URIs — machine-readable dietary
  classification

---

## 2. VideoObject schema (standalone — for YouTube-first discovery)

Separate from the Recipe schema's embedded video. Published as its own
JSON-LD block to maximise video search surface area.

```json
{
  "@context": "https://schema.org",
  "@type": "VideoObject",
  "name": "[Recipe title] — toddler-adapted recipe by [Creator]",
  "description": "PrepLink adapted this recipe for toddler safety. Covers 38% of daily iron target. Build your Instacart cart in one tap.",
  "thumbnailUrl": [
    "https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
    "https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
  ],
  "uploadDate": "{video_upload_date}",
  "duration": "PT1M23S",
  "contentUrl": "https://www.youtube.com/watch?v={video_id}",
  "embedUrl": "https://www.youtube.com/embed/{video_id}",
  "publisher": {
    "@type": "Organization",
    "name": "PrepLink",
    "logo": {
      "@type": "ImageObject",
      "url": "https://preplink.app/logo-schema.png"
    }
  },
  "potentialAction": {
    "@type": "ViewAction",
    "target": "https://preplink.app/recipe/{slug}"
  }
}
```

---

## 3. FAQPage schema (nutrition hub pages)

Enables FAQ rich results for parent nutrition queries. Applied to
`/nutrition/[nutrient]` hub pages.

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "How much iron does a toddler need per day?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Toddlers aged 1–3 years need 7mg of iron per day according to USDA Dietary Reference Intakes 2025. Most toddlers get significantly less than this. Iron from plant sources (non-haem iron) is best absorbed when paired with vitamin C — for example, spinach with red pepper or lentils with tomato sauce."
      }
    },
    {
      "@type": "Question",
      "name": "What are the best high-iron foods for toddlers?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "The best iron sources for toddlers include red lentils, black beans, tofu, beef, chicken, pumpkin seeds, fortified oat cereal, spinach, and peas. PrepLink scores every recipe against toddler iron targets and flags recipes that cover more than 30% of the daily target."
      }
    },
    {
      "@type": "Question",
      "name": "Does vitamin C really help with iron absorption?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Yes. Vitamin C (ascorbic acid) converts non-haem iron (found in plants) into a form the body absorbs more easily. Adding red pepper, tomato, lemon juice, or strawberries to an iron-rich meal can increase absorption by 2–4 times. PrepLink automatically flags this pairing in its nutrition brief."
      }
    },
    {
      "@type": "Question",
      "name": "Can too much calcium block iron absorption?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Calcium can inhibit iron absorption when consumed together in the same meal. If your toddler is eating iron-rich legumes or leafy greens, consider serving dairy (milk, cheese, yogurt) at a different meal. PrepLink flags this interaction in the cart view when both are present."
      }
    }
  ]
}
```

---

## 4. BreadcrumbList schema (all pages)

```json
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {
      "@type": "ListItem",
      "position": 1,
      "name": "Home",
      "item": "https://preplink.app"
    },
    {
      "@type": "ListItem",
      "position": 2,
      "name": "Toddler recipes",
      "item": "https://preplink.app/for/toddler"
    },
    {
      "@type": "ListItem",
      "position": 3,
      "name": "High-iron recipes",
      "item": "https://preplink.app/nutrition/iron"
    },
    {
      "@type": "ListItem",
      "position": 4,
      "name": "Spinach and Lentil Soup",
      "item": "https://preplink.app/recipe/spinach-lentil-soup-toddler-iron"
    }
  ]
}
```

---

## 5. Diet schema (clinical/dietary context pages)

Applied when `metadata.is_baby_led_weaning = true` or
`metadata.target_audience = "keto"`.

### Baby-Led Weaning

```json
{
  "@context": "https://schema.org",
  "@type": "Diet",
  "name": "Baby-Led Weaning",
  "alternateName": "BLW",
  "description": "Baby-Led Weaning is a method of introducing solid foods that skips purees and allows infants from approximately 6 months to self-feed soft finger foods. It supports motor skill development, appetite regulation, and a positive relationship with food.",
  "url": "https://preplink.app/for/9-12m",
  "suitableForDiet": "https://schema.org/Diet"
}
```

### Ketogenic diet

```json
{
  "@context": "https://schema.org",
  "@type": "Diet",
  "name": "Ketogenic Diet",
  "description": "A high-fat, low-carbohydrate dietary pattern that limits net carbohydrates to typically under 20–50g per day. PrepLink keto recipes are scored to ensure net carbs per serving remain within this threshold.",
  "suitableForDiet": "https://schema.org/KetogenicDiet",
  "url": "https://preplink.app/for/keto"
}
```

---

## 6. Organization schema (homepage only)

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "PrepLink",
  "url": "https://preplink.app",
  "description": "Nutrition-first meal planning for families. Convert any YouTube recipe to an age-adapted, pantry-aware Instacart cart in one tap.",
  "logo": {
    "@type": "ImageObject",
    "url": "https://preplink.app/logo-schema.png",
    "width": 512,
    "height": 512
  },
  "contactPoint": {
    "@type": "ContactPoint",
    "contactType": "customer support",
    "email": "support@preplink.app"
  },
  "sameAs": [
    "https://twitter.com/preplink",
    "https://instagram.com/preplink",
    "https://www.linkedin.com/company/preplink"
  ]
}
```

---

## 7. Creator attribution page schema (/creator/[handle])

```json
{
  "@context": "https://schema.org",
  "@type": "Person",
  "name": "[Creator display name]",
  "alternateName": "@{handle}",
  "url": "https://youtube.com/@{handle}",
  "sameAs": [
    "https://youtube.com/@{handle}",
    "https://preplink.app/creator/{handle}"
  ],
  "description": "Recipes by [Creator], adapted for family nutrition by PrepLink.",
  "image": "{creator_profile_image_url}"
}
```

---

## 8. Implementation in RecipeStructuredData.tsx

```typescript
// components/seo/RecipeStructuredData.tsx

import type { ClinicallySafeRecipe } from "@/types/clinical";

interface Props {
  recipe: ClinicallySafeRecipe;
  slug: string;
  pageUrl: string;
  createdAt: string;
  updatedAt: string;
}

export function RecipeStructuredData({ recipe, slug, pageUrl, createdAt, updatedAt }: Props) {
  const { metadata, recipe: recipeSummary, cart_payload } = recipe;

  const allIngredients = [
    ...cart_payload.fresh_ingredients,
    ...cart_payload.pantry_staples,
  ].map(i => `${i.quantity} ${i.unit} ${i.name}`.trim());

  // Recipe schema
  const recipeSchema = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    name: `${recipeSummary.title} — adapted for ${audienceLabel(metadata.target_audience)}`,
    description: metadata.clinical_artifact_reasoning,
    image: [metadata.infographic_url],
    author: {
      "@type": "Person",
      name: metadata.creator_handle ?? "Unknown creator",
      url: metadata.creator_handle
        ? `https://youtube.com/@${metadata.creator_handle}`
        : undefined,
    },
    publisher: {
      "@type": "Organization",
      name: "PrepLink",
      url: "https://preplink.app",
    },
    datePublished: createdAt,
    dateModified: updatedAt,
    recipeIngredient: allIngredients,
    recipeInstructions: recipeSummary.instructions.map((text, i) => ({
      "@type": "HowToStep",
      position: i + 1,
      text,
    })),
    // nutrition, video, suitableForDiet populated from recipe data
  };

  // Video schema (if YouTube source)
  const ytMatch = metadata.original_url.match(/(?:v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  const videoSchema = ytMatch ? {
    "@context": "https://schema.org",
    "@type": "VideoObject",
    name: `${recipeSummary.title} — original video`,
    thumbnailUrl: `https://i.ytimg.com/vi/${ytMatch[1]}/maxresdefault.jpg`,
    embedUrl: `https://www.youtube.com/embed/${ytMatch[1]}`,
    contentUrl: metadata.original_url,
  } : null;

  // Diet schema (BLW or keto)
  const dietSchema = metadata.is_baby_led_weaning
    ? buildBLWSchema()
    : metadata.target_audience === "keto"
    ? buildKetoSchema()
    : null;

  // Breadcrumb schema
  const breadcrumbSchema = buildBreadcrumb(metadata.target_audience, recipeSummary.title, pageUrl);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(recipeSchema) }}
      />
      {videoSchema && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(videoSchema) }}
        />
      )}
      {dietSchema && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(dietSchema) }}
        />
      )}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbSchema) }}
      />
    </>
  );
}
```

---

## 9. Validation and testing

### Before every deploy

```bash
# Test structured data for a sample recipe
curl https://preplink.app/recipe/spinach-lentil-soup-toddler-iron \
  | grep -o '<script type="application/ld+json">.*</script>'

# Validate with Google's Rich Results Test
# https://search.google.com/test/rich-results
# Expected: Recipe card, VideoObject, Breadcrumb all pass
```

### Schema validation checklist

- [ ] Recipe schema: name, recipeIngredient, recipeInstructions all present
- [ ] Image field is absolute URL (not relative)
- [ ] `datePublished` in ISO-8601 format
- [ ] VideoObject: `thumbnailUrl` is accessible (returns 200)
- [ ] BreadcrumbList: `item` URLs are canonical (https, not http)
- [ ] No `undefined` values serialised as JSON (use `|| null` guards)
- [ ] Multiple `<script type="application/ld+json">` blocks are separate
  scripts, not comma-separated within one block

### Google Search Console monitoring

- Recipe rich results: Performance → Search type: Web → Filter by recipe
- Video results: Search type: Video — track impressions for YouTube-sourced recipes
- FAQ results: Track impressions for nutrition hub pages
- Core Web Vitals: Ensure LCP <1.2s on mobile (LCP element is the hero image)
