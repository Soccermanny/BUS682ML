# Phase 1 Reissue — Corrected Prompt Guide
**Focus: Domestic Box Office Only**  
**Dataset: project_2_data_corrected.csv**  
**Date: April 6, 2026**

---

## What Changed From the Previous Run

| Issue | Previous Run | Corrected Run |
|-------|-------------|---------------|
| Dataset | project_2_data_filled_with_api.csv (pre-filled, single country) | project_2_data_corrected.csv (full multi-country, filter to Domestic) |
| Baseline predictors | 377 (factors accidentally included) | 71 (year + runtime + genres + language only) |
| Target variable | Inconsistent across files | log(1 + box_office) everywhere, no exceptions |
| Scope | Box office + ratings + composite | Box office only |
| Cross-outcome file | Wrong scale (raw BO used) | Not needed — BO only |

---

## Key Parameters (Do Not Change These)

```
Target variable    : log(1 + box_office)  — always, no exceptions
Filter             : country == 'Domestic' only → 3,438 films
Deduplication      : imdb_id is already unique in Domestic subset — no dedup needed
Cross-validation   : 5-fold, report mean and std
Bonferroni threshold: 0.05 / 30 = 0.001667
Significance tiers :
    STRONG     → p < 0.001667
    SUGGESTIVE → 0.001667 ≤ p < 0.05
    WEAK       → p ≥ 0.05
Baseline A sample  : 3,438 films (all Domestic)
Baseline B sample  : 2,694 films (Domestic where production_budget is not null)
Excluded variables : imdb_votes, imdb_rating — POST-RELEASE, never include in any model
```

---

## STEP 0 — Context Block (Paste This First in Every Session)

```
You are a data scientist working on a movie box office prediction project.
Read and retain this full context before doing anything else.

DATASET: project_2_data_corrected.csv
- Filter immediately to country == 'Domestic' → 3,438 unique films, no duplicates
- Do not use any other country rows for any analysis

TARGET VARIABLE: log(1 + box_office)
- Always use this. Never use raw box_office as a target. Never use imdb_rating as a target.
- This is the ONLY outcome variable for this entire analysis.

COLUMNS AVAILABLE:
- box_office: US domestic revenue in USD
- production_budget: film production cost (missing for 744 films)
- release_year, runtime, genres (comma-separated), original_language
- Factor_0 through Factor_29: 30 latent content factors
- imdb_rating, imdb_votes: DO NOT USE IN ANY MODEL — post-release variables

ENCODING RULES (apply consistently to every model):
- genres: multi-hot encode by splitting on comma → 24 binary columns
- original_language: one-hot encode → 45 binary columns (drop most frequent: 'en')
- release_year: include as a single numeric variable
- runtime: include as a single numeric variable
- production_budget (when used): apply log(1 + production_budget) transformation

CORRECT PREDICTOR COUNTS:
- Baseline A: 71 predictors (release_year, runtime, 24 genre dummies, 45 language dummies)
- Baseline B: 72 predictors (Baseline A + log_production_budget)
- Model A+: 101 predictors (Baseline A + 30 factors)
- Model B+: 102 predictors (Baseline B + 30 factors)
If your predictor count differs from these numbers, stop and recheck your encoding.

CROSS-VALIDATION: 5-fold, report CV R² as mean ± std across folds
BONFERRONI THRESHOLD: 0.05 / 30 = 0.001667

VERDICT LOGIC FOR EACH FACTOR (apply strictly):
- STRONG POSITIVE : BO coefficient positive AND Bonferroni tier = STRONG AND Stability = STABLE
- STRONG NEGATIVE : BO coefficient negative AND Bonferroni tier = STRONG AND Stability = STABLE
- SUGGESTIVE      : Bonferroni tier = SUGGESTIVE (regardless of stability)
- MIXED           : Stability = UNSTABLE (sign flips under Ridge), regardless of p-value
- WEAK            : Bonferroni tier = WEAK

A factor that is UNSTABLE cannot be STRONG POSITIVE or STRONG NEGATIVE under any circumstances.

Acknowledge this context and confirm the domestic row count is 3,438 before proceeding.
```

---

## STEP 1 — Exploratory Data Analysis

```
Step 1: Exploratory Data Analysis on the Domestic subset (3,438 films).

Run the following and report results in clean summary tables:

1. BOX OFFICE DISTRIBUTION (raw)
   Report: count, mean, median, std, min, max, skewness
   Confirm: skewness > 1.5 justifies log transformation

2. LOG BOX OFFICE DISTRIBUTION
   Apply: log_box_office = log(1 + box_office)
   Report: count, mean, median, std, min, max, skewness
   Confirm: skewness is closer to 0 than raw box_office

3. PRODUCTION BUDGET COVERAGE
   Report: how many films have budget (not null) vs missing
   Report: mean and median budget for non-missing films only

4. FACTOR VARIANCE CHECK
   For each of the 30 factors, report mean and std.
   Flag any factor where std < 0.3 as LOW VARIANCE.

5. FACTOR INTERCORRELATION
   Among the 30 factors only, compute the correlation matrix.
   Report: how many pairs have |correlation| > 0.5
   List the top 5 most correlated pairs with their correlation values.
   Note: high intercorrelation means Bonferroni may be overly conservative.

6. GENRE AND LANGUAGE ENCODING VERIFICATION
   After encoding genres (multi-hot) and original_language (one-hot, drop 'en'):
   Confirm: genre dummy columns = 24
   Confirm: language dummy columns = 45
   If either count differs, report what you found and why.

Output format: one table per section. No charts needed.
```

**Expected output:** Stats tables for box office, log box office, budget coverage,
factor variance flags, top 5 correlated factor pairs, and encoding confirmation.

---

## STEP 2 — Baseline Models (Box Office Only)

```
Step 2: Build two OLS baseline models predicting log(1 + box_office).
Use 5-fold cross-validation for all R² reporting.

These models must contain ONLY the following predictors.
Do NOT include imdb_votes, imdb_rating, production_budget (in Baseline A),
money_success_ratio, money_success_score, or any Factor columns.

BASELINE A — No budget (3,438 films):
Predictors:
  - release_year (numeric, 1 column)
  - runtime (numeric, 1 column)
  - genres multi-hot encoded (24 binary columns, split on comma)
  - original_language one-hot encoded (45 columns, drop 'en' as reference)
Total predictors: 71
Print predictor count before fitting. If count ≠ 71, stop and fix encoding.

BASELINE B — With budget (2,694 films where production_budget is not null):
Predictors: all 71 from Baseline A, plus log(1 + production_budget)
Total predictors: 72
Print predictor count before fitting. If count ≠ 72, stop and fix encoding.

For EACH model report:
  - Predictor count (must match targets above)
  - Sample size
  - In-sample R²
  - Adjusted R²
  - CV R² mean (5-fold)
  - CV R² std (5-fold)
  - RMSE on log scale

Output as a single comparison table with Baseline A and Baseline B as columns.
```

**Expected output:** A 7-row table with Baseline A and B metrics side by side.
Baseline A should have ~71 predictors and CV R² roughly in the 0.15–0.35 range
without the factors inflating it.

---

## STEP 3 — Factor-Augmented Models (Box Office Only)

```
Step 3: Build two factor-augmented OLS models by adding all 30 factors
to the baselines from Step 2. Predict log(1 + box_office).

MODEL A+ — Baseline A predictors + Factor_0 through Factor_29 (3,438 films)
Total predictors: 101
Print predictor count. If count ≠ 101, stop and fix.

MODEL B+ — Baseline B predictors + Factor_0 through Factor_29 (2,694 films)
Total predictors: 102
Print predictor count. If count ≠ 102, stop and fix.

PART A — Model performance table:
For each model report the same metrics as Step 2 (predictor count, sample size,
in-sample R², adjusted R², CV R² mean, CV R² std, RMSE).
Then add two delta rows:
  - Δ CV R² = Model A+ minus Baseline A (and B+ minus Baseline B)
  - Δ Adjusted R² = same comparison

PART B — F-test for each augmented model vs its baseline:
Report F-statistic and p-value for both comparisons.
(Tests whether adding the 30 factors significantly improves fit)

PART C — Factor coefficient table (for BOTH Model A+ and Model B+):
For every factor (Factor_0 through Factor_29) report:
  - Factor name
  - OLS coefficient (Model A+)
  - Standard error (Model A+)
  - p-value (Model A+)
  - Bonferroni tier (Model A+): STRONG / SUGGESTIVE / WEAK
  - OLS coefficient (Model B+)
  - p-value (Model B+)
  - Bonferroni tier (Model B+)

Sort the table by absolute value of Model A+ coefficient, descending.
Export this table as a CSV called: factor_coeff_boxoffice.csv
```

**Expected output:** Performance table with delta rows, two F-test results,
and a full 30-row factor coefficient table exported to CSV.

---

## STEP 4 — Ridge Regression Robustness Check

```
Step 4: Repeat the factor-augmented models using Ridge regression
to test coefficient stability. This checks whether OLS results hold
under regularization, which handles multicollinearity.

Use RidgeCV with alphas = [0.01, 0.1, 1, 10, 100].
Use 5-fold cross-validation for alpha selection.

Run two Ridge models:
  RIDGE A+ : same predictors as Model A+ (3,438 films)
  RIDGE B+ : same predictors as Model B+ (2,694 films)

For each Ridge model report:
  - Optimal alpha selected
  - CV R² (RidgeCV score)
  - In-sample R²

Then produce a stability comparison table for the 30 factors
using Model A+ (OLS) vs Ridge A+ only:

Columns:
  - Factor name
  - OLS coefficient (Model A+)
  - Ridge coefficient (Ridge A+)
  - % change = |OLS - Ridge| / |OLS| × 100
  - Direction match: YES if same sign, NO if sign flips
  - Stability flag:
      STABLE   → Direction match = YES AND % change < 30%
      UNSTABLE → Direction match = NO OR % change ≥ 30%

Sort by % change descending so most unstable factors appear first.
Export as: ridge_ols_comparison_corrected.csv

IMPORTANT: Apply the verdict logic from the context block.
Any factor with Stability = UNSTABLE must NOT receive a
STRONG POSITIVE or STRONG NEGATIVE verdict in the master table.
```

**Expected output:** Ridge summary metrics for A+ and B+, plus a 30-row
stability table sorted by instability. Factors that flip sign here are
unreliable and must be flagged as MIXED in the final master table.

---

## STEP 5 — Master Coefficient Table and Phase 1 Conclusion

```
Step 5: Compile all results into the final Phase 1 output for box office.

PART A — Master coefficient table (30 rows, one per factor):
Columns:
  - Factor (Factor_0 through Factor_29)
  - Factor Name (use the provided factor name mapping)
  - OLS Coef (Model A+)
  - Bonf Tier (Model A+): STRONG / SUGGESTIVE / WEAK
  - OLS Coef (Model B+)
  - Bonf Tier (Model B+)
  - Stability: STABLE or UNSTABLE (from Step 4)
  - Overall Verdict (apply strictly per rules below)

VERDICT RULES — apply these exactly, in order:
  1. If Stability = UNSTABLE → verdict = MIXED (no exceptions)
  2. If Stability = STABLE AND Bonf Tier A+ = STRONG AND OLS Coef A+ > 0 → STRONG POSITIVE
  3. If Stability = STABLE AND Bonf Tier A+ = STRONG AND OLS Coef A+ < 0 → STRONG NEGATIVE
  4. If Bonf Tier A+ = SUGGESTIVE → SUGGESTIVE
  5. All others → WEAK

Sort by absolute OLS Coef (Model A+) descending.
Export as: PHASE1_MASTER_TABLE_CORRECTED.csv

PART B — Model performance summary table:
One table showing all 4 models side by side:
  Baseline A | Model A+ | Baseline B | Model B+
Rows: Sample size, Predictors, In-sample R², Adjusted R², CV R² mean, CV R² std, RMSE, Δ CV R²

PART C — Written conclusion (3–4 sentences):
Answer the Phase 1 question directly:
Do the 30 content factors add statistically significant and practically
meaningful predictive value for domestic box office revenue, above and
beyond what is already known from genre, language, runtime, release year,
and production budget? Reference the delta CV R², F-test result, and
number of Bonferroni-significant factors in your answer.

PART D — Top findings (4 bullet points max):
  - Which factors are STRONG POSITIVE (stable, significant, positive)?
  - Which factors are STRONG NEGATIVE (stable, significant, negative)?
  - Which factors are MIXED (unstable under Ridge)?
  - Any notable pattern in what the strong factors represent?

PART E — Limitations (keep to 4 bullet points):
  - Missing budget data (n=744) and its effect on Baseline B sample
  - Bonferroni conservatism given factor intercorrelations
  - Coefficients are associations not causal effects
  - Temporal stability not assessed (dataset spans 1932–2023)
```

**Expected output:** The master CSV, a 4-model performance table, a written
conclusion paragraph, 4 finding bullets, and 4 limitation bullets.
This is the complete Phase 1 deliverable.

---

## Factor Name Mapping (Include in Every Session)

Paste this dictionary into Haiku at the start so it can label factors correctly:

```python
factor_names = {
    'Factor_0':  'Puzzle-Driven Storytelling and Unexpected Turns',
    'Factor_1':  'Childlike Wonder / Family-Friendliness',
    'Factor_2':  'Inner Turmoil and Emotional Struggle',
    'Factor_3':  'Documentary-style Storytelling',
    'Factor_4':  'Avant-Garde',
    'Factor_5':  'Comedy, Humor, and Social Satire',
    'Factor_6':  'Romantic Courtship / Relationship Drama',
    'Factor_7':  'Triumph Over Adversity',
    'Factor_8':  'Futuristic Science and Technology',
    'Factor_9':  'War and Political History',
    'Factor_10': 'Music and Performance as Storytelling',
    'Factor_11': 'Adrenaline-Fueled Action and Heroic Combat',
    'Factor_12': 'Magical World / Mythic Adventure',
    'Factor_13': 'Growing Up and Coming of Age',
    'Factor_14': 'Justice, Law, and Criminal Investigation',
    'Factor_15': 'Family Bonds and Parent-Child Relationships',
    'Factor_16': 'East Asian Cultural Setting',
    'Factor_17': 'Sexual Themes',
    'Factor_18': 'Portrait of Extraordinary Life',
    'Factor_19': 'Greed, Ambition, and Financial Crime',
    'Factor_20': 'Female Perspective and Empowerment',
    'Factor_21': 'Fear and Psychological Horror',
    'Factor_22': 'Classic Hollywood Era Style',
    'Factor_23': "Nature's Majesty and Peril",
    'Factor_24': 'Black Identity & Experience',
    'Factor_25': 'Faith and Spiritual Awakening',
    'Factor_26': 'Showmanship and Staged Spectacle',
    'Factor_27': 'LGBTQ+ Identity and Relationships',
    'Factor_28': 'Latino Cultural Perspective',
    'Factor_29': 'Competitive Sports',
}
```

---

## Files to Return After Each Step

| Step | File(s) to return |
|------|-------------------|
| Step 0 | Confirmation message with row count (3,438) |
| Step 1 | EDA tables pasted inline |
| Step 2 | baseline_models_corrected.csv |
| Step 3 | factor_coeff_boxoffice.csv + performance table inline |
| Step 4 | ridge_ols_comparison_corrected.csv |
| Step 5 | PHASE1_MASTER_TABLE_CORRECTED.csv + written conclusion inline |

---

## Quick Validation Checklist (Run After Each Step)

After Step 2 — confirm:
- [ ] Baseline A predictor count = 71
- [ ] Baseline B predictor count = 72
- [ ] Neither baseline contains any Factor column
- [ ] Neither baseline contains imdb_votes or imdb_rating

After Step 3 — confirm:
- [ ] Model A+ predictor count = 101
- [ ] Model B+ predictor count = 102
- [ ] Delta CV R² is positive (factors improve over baseline)
- [ ] F-test p-value < 0.05 for both augmented models

After Step 4 — confirm:
- [ ] Stability flags are present for all 30 factors
- [ ] Any factor with Direction match = NO is flagged UNSTABLE

After Step 5 — confirm:
- [ ] No UNSTABLE factor has verdict STRONG POSITIVE or STRONG NEGATIVE
- [ ] Master table has exactly 30 rows
- [ ] PHASE1_MASTER_TABLE_CORRECTED.csv exported successfully
