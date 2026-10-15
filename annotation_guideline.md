# Annotation Guideline: Dish-Level Sentiment in Thai Restaurant Reviews

This is the guideline used to build the benchmark. Each review was labeled for (1) whether
it names a specific dish, (2) the dish names, and (3) one sentiment label per dish.

## 1. Decision flow

**Step 1: Does the review name a specific dish?** Set `has_dish` = `Y` or `N`. If `N`,
the review has no dish rows.

**Step 2: List every named dish.** Copy each name exactly as the reviewer wrote it (Thai
or English). Do not translate, correct spelling, or normalize. Order does not matter:
evaluation compares sets of dishes per review.

**Step 3: Assign one sentiment label per dish.**

| Label | Meaning |
|---|---|
| `POS` | Clear positive opinion about that dish (taste, texture, freshness, portion, temperature) |
| `NEG` | Clear negative opinion about that dish |
| `NEU` | Dish is mentioned or ordered, but no clear opinion is stated |
| `MIX` | Both a positive and a negative point about the same dish |

**Hedge words.** If the only description is one of งั้นๆ, กลางๆ, พอใช้, ธรรมดา, ปกติ,
เฉยๆ, โอเค, label `NEU` (not `NEG`).

**Bare taste words.** Words such as เผ็ด, หวาน, เค็ม, เปรี้ยว, มัน without an evaluative
qualifier are `NEU`. With a qualifier they become `POS` or `NEG`: "เผ็ด" → NEU;
"เผ็ดอร่อย", "เผ็ดกำลังดี" → POS; "เผ็ดเกินไป" → NEG.

**Signature-menu items.** For a dish named in a "เมนูเด็ด:" / "เมนูแนะนำ:" summary line:
- If the review comments on that dish elsewhere (also under a slightly different name, or
  as "จานนี้"), label that comment with the rules above.
- If it is named only in the summary line, with no dish-specific comment, label it `POS`:
  the reviewer selected it as a highlight, which is treated as an implicit endorsement.
  General praise of the restaurant or of the food overall is not a dish-specific comment.
- The released file also gives the alternative convention (`NEU` for such items) in the
  column `sentiment_alt_neu`; see the paper, Sections 3.3 and 5.2.

## 2. What counts as a dish

- **Include** specific menu items (e.g. ผัดไทย, ต้มยำกุ้ง, ข้าวมันไก่, คาโบนาร่า).
- **Exclude** generic terms with no named item (อาหาร, ของหวาน): a review that only says
  "อาหารอร่อย" is `has_dish = N`.
- **Exclude** drinks.
- **Exclude** non-food aspects (service, atmosphere, price, parking, waiting time).

## 3. Judge the dish, not the restaurant

Only the opinion about the dish itself counts. "ผัดไทยอร่อยแต่บริการช้า" → ผัดไทย = `POS`;
the comment about service is ignored.

## 4. Edge cases

- The same dish mentioned twice with the same sentiment is recorded once.
- If the star rating and the text about a dish disagree, follow the text about the dish.
- Structured reviews that rate each dish with a symbol scale (e.g. 🌕🌕🌕🌗🌑) plus a short
  descriptor count as `has_dish = Y`; infer the label from the rating and the descriptor
  (about 4/5 + "เข้ากันดี" → `POS`; about 3/5 + "พอได้" → `NEU`).
- Misspelled or slang dish names are kept exactly as written.

## 5. Sample construction

300 candidate reviews (150 Wongnai, 150 Google Maps, Bangkok metropolitan area) were drawn
at random (seed 42) from reviews 30–500 characters long (40–500 for Wongnai) containing at
least one of 25 Thai taste/quality cue words (อร่อย, ไม่อร่อย, รสชาติ, เผ็ด, หวาน, เค็ม,
เปรี้ยว, จืด, กรอบ, นุ่ม, เหนียว, แน่น, สด, หอม, มัน, กลิ่น, คาว, แซ่บ, กลมกล่อม, ชุ่มฉ่ำ,
แห้ง, เละ, ดิบ, ไหม้, ล้น), then shuffled so platform was not visible during labeling.
This is a keyword-filtered convenience sample, not a uniform random sample.
