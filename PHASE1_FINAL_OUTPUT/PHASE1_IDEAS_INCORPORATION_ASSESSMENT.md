# Phase 1 Analysis: Incorporation of User Ideas

**Date:** April 6, 2026  
**Status:** Project 2 Phase 1 Complete

---

## IDEA MATRIX: What Was Incorporated vs. What's Available for Phase 2

### ✅ IDEAS FULLY IMPLEMENTED IN PHASE 1

| Idea | Implementation | Location |
|------|----------------|----------|
| **Weight of each factor towards box office and ratings separately** | All 30 factors analyzed with separate OLS models for box office, IMDB rating, and composite score. Coefficients, standard errors, t-statistics, and Bonferroni p-values computed for each outcome. | [PHASE1_MASTER_COEFFICIENT_TABLE.csv](PHASE1_MASTER_COEFFICIENT_TABLE.csv) <br> Columns: OLS Coef (BO), OLS Coef (Rating), OLS Coef (Composite) |
| **Create composite "success score" combining ratings and box office** | Composite score = 0.5 × z(log box office) + 0.3 × z(IMDB rating) + 0.2 × z(ROI) with 2,694 films having full data and 744 rescaled using BO+Rating only. Cross-validated OLS regression on factors achieved CV R² = 0.194 with 19/30 factors Bonferroni-significant. | [composite_scores.csv](composite_scores.csv) <br> [PHASE1_SUMMARY.md](PHASE1_SUMMARY.md) Section 1 & 2 |
| **Control group for testing weights** | Baseline models created for comparison: Baseline A (BO with controls only), Baseline B (Rating with controls only). Demonstrates factor value-add of +16.7 pp for BO and +14.3 pp for ratings. | [PHASE1_SUMMARY.md](PHASE1_SUMMARY.md) Section 1 <br> Tables showing Δ CV R² vs. baselines |
| **Separate analysis revealing commercial-critical tensions** | Identified factors with divergent effects: Factor_3 (+0.37 BO, -0.90 rating), Factor_8 (+0.24 BO, -0.80 rating), Factor_2 (-0.02 BO, +1.71 rating) showing BO ≠ critical acclaim. | [PHASE1_SUMMARY.md](PHASE1_SUMMARY.md) Section 3, Finding #2 <br> [PHASE1_MASTER_COEFFICIENT_TABLE.csv](PHASE1_MASTER_COEFFICIENT_TABLE.csv) "Overall Verdict" column |

---

### ⏳ IDEAS READY FOR PHASE 2 (Infrastructure in Place)

| Idea | Current State | Next Steps | Data Needed |
|------|---------------|-----------|------------|
| **Reverse factor analysis**: Decode what the 30 dimensionally-reduced factors actually represent | Factors are opaque black-box features. No loading interpretation done yet. | Compute factor loadings on original variables: budget, production company, cast quality, marketing spend, release timing, etc. PCA loading analysis or correlation matrix with original features. | Original (non-PCA-reduced) feature matrix |
| **Fill missing MPAA ratings from outside sources** | Not attempted. Data set has IMDB ratings but MPAA rating (G/PG/PG-13/R) not visible in current analysis. | Web scrape MPAA ratings from TMDB API or OMDB API. Merge by movie ID/title. | MPAA rating API access (TMDB, OMDB) |
| **Fill missing production budgets (n=744)** | Acknowledged in limitations. Missing budget affects composite score calculation and ROI analysis. | Use web scraping (TMDB, Box Office Mojo, Wikipedia) or statistical imputation (multivariate regression on genre, cast, runtime, release date). Create sensitivity check comparing full-data vs. imputed results. | Budget reference data source (TMDB, BOX, Wikipedia) |
| **Control group creation** | Baseline models created for cross-validation, but no explicit hold-out test set reserved. All data used for fitting + CV. | Create explicit 70-15-15 or 80-10-10 train-validation-test split. Fit models on train, optimize hyperparameters on validation, report final metrics on hold-out test set. | Data split strategy & test harness |

---

### 🚀 IDEAS NOT YET ADDRESSED (High-Value Phase 2 Candidates)

#### 1. **NLP on Movie Descriptions**
**Concept:** Extract keywords, themes, sentiment, linguistic patterns from plot summaries to identify success drivers  
**Potential Insight:** Are certain narrative archetypes or emotional tones (adventure, romance, thriller) more predictive than baseline genre dummies?

**Implementation Path:**
```python
# Pseudo-code
from sklearn.feature_extraction.text import TfidfVectorizer
from textblob import TextBlob

# Get descriptions for all 3,438 films
descriptions = df['overview'].fillna('')

# Option A: Bag-of-words TF-IDF
tfidf = TfidfVectorizer(max_features=100, stop_words='english')
tfidf_features = tfidf.fit_transform(descriptions)

# Option B: Sentiment analysis
sentiments = [TextBlob(desc).sentiment.polarity for desc in descriptions]

# Option C: Keyword extraction (YAKE or spaCy)
keywords = extract_keywords(descriptions)

# OLS regression: BOX_OFFICE ~ 30_factors + tfidf_features
# Report: Does text add to prediction? Which keywords are most important?
```

**Data Required:** Movie plot descriptions/overviews (already in dataset as `overview` column)  
**Estimated Value-Add:** 2-5% increase in CV R² if language patterns are predictive  
**Timeline:** 2-3 hours implementation

---

#### 2. **Key Moments & Mood Analysis**
**Concept:** Identify narrative structure (act breaks, climaxes, pacing) and emotional palette from descriptions  
**Potential Insight:** Films with "epic journeys" or "emotional climaxes" may exceed expectations; "formulaic" films may underperform despite big budgets

**Implementation Path:**
```python
# Pseudo-code
# Define key mood/moment categories based on description keywords
mood_keywords = {
    'epic': ['epic', 'legendary', 'grand', 'massive'],
    'emotional': ['heartfelt', 'touching', 'moving', 'emotional'],
    'dark': ['dark', 'gritty', 'noir', 'sinister'],
    'comedic': ['hilarious', 'funny', 'comedy', 'witty'],
    'romantic': ['romance', 'love', 'passion', 'romantic']
}

# Count keyword matches per description
for mood, keywords in mood_keywords.items():
    df[f'mood_{mood}_score'] = df['overview'].apply(
        lambda x: sum(x.lower().count(kw) for kw in keywords)
    )

# OLS regression: BOX_OFFICE ~ 30_factors + mood_scores
# Report: Which moods command premium pricing? Are moods correlated with ratings?
```

**Data Required:** Plot descriptions (already have)  
**Estimated Value-Add:** 3-7% increase in CV R² depending on mood signal strength  
**Timeline:** 1-2 hours implementation

---

#### 3. **Actor & Director Weight Analysis** (HIGH PRIORITY)
**Concept:** Compute individual contribution of lead actor/director to film success via their salary and historical performance  
**Potential Insight:** A-list talent commands premium revenue; star power drives both BO and critical acclaim OR doesn't correlate once factors control for production quality

**Implementation Path:**
```python
# Data structure needed:
df_cast_crew = pd.read_csv('cast_crew_data.csv')
# Columns: movie_id, person_id, person_name, role (actor/director), salary, 
#          person_avg_box_office, person_avg_rating, total_films

# For each film, aggregate top 3 actors + director:
df['lead_actor_salary'] = df.movie_id.map(lambda x: get_top_actor_salary(x, n=1))
df['top_3_actors_salary'] = df.movie_id.map(lambda x: sum of top 3 actor salaries)
df['director_salary'] = ...
df['lead_actor_avg_historical_rating'] = ...
df['actor_cost_pct_of_budget'] = df['top_3_actors_salary'] / df['production_budget']

# OLS regression models:
# Model D: BOX_OFFICE ~ 30_factors + actor_salaries + director_salary + actor_historical_performance
# Model E: IMDB_RATING ~ 30_factors + actor_historical_rating + director_historical_rating

# Report:
# - Does adding cast/crew data improve CV R²?
# - Is actor salary correlated with both BO and rating? (If yes → star power; if only BO → premium pricing)
# - Does director track record predict ratings better than factors alone?
# - What's the ROI on A-list talent? (Does +$20M actor salary → +$50M BO?)
```

**Data Required:**
- Cast/crew salary info (TMDB has some, but likely incomplete)
- Cast/crew historical performance metrics (average BO/rating of all their films)
- This data may need to be scraped or licensed

**Estimated Value-Add:** 5-12% increase in CV R² if talent is predictive  
**Timeline:** 4-6 hours including data collection  
**Business Impact:** **HIGHEST** — actionable for greenlight decisions ("Should we pay for this director?")

---

#### 4. **Reverse Factor Analysis: Decode the Black Box**
**Concept:** PCA extracted 30 latent factors. What do they represent? Are they "production quality," "marketing intensity," "star power," "screenplay quality," etc.?

**Implementation Path:**
```python
# Assume original feature matrix (before PCA) still available
# Features might be: budget, cast_avg_rating, runtime, production_company_prestige, 
#                   marketing_spend, release_season, competition_count, etc.

# Load the PCA transformation matrix (eigenvectors)
pca_model = load_pca_model()  # or reverse-engineer from factors

# Compute loadings: correlation between original features and factors
loadings = original_features.corr(factors_dataframe)
# Shape: (n_original_features, 30)

# Interpret each factor:
# Factor_0: high loading on [budget, cast_salary, runtime] → "Production Scale"
# Factor_14: high loading on [marketing_spend, weeks_in_theater] → "Market Saturation"
# etc.

# Report:
# - Factor naming/interpretation (50 sentences max per factor)
# - Which original variables drive each factor?
# - How do interpretable factors compare to opaque factor coefficients?
```

**Data Required:** Original (pre-PCA) feature matrix  
**Estimated Value-Add:** 50% increase in business interpretability (same predictive power, but explainable)  
**Timeline:** 2-3 hours if original features available, 8-10 hours if features need reconstruction  
**Business Impact:** **CRITICAL** — without this, recommendations cannot be operationalized

---

### 📊 COMPARISON TABLE: What Analysis Reveals

| Dimension | Phase 1 Finding | Phase 2 Hypothesis |
|-----------|-----------------|-------------------|
| **Factor importance** | Factor_0, 1, 7, 14 strongest; Factor_16, 26, 17, 20 most negative | Does Factor_0 = "Star Power"? Does Factor_16 = "Script Quality Issues"? |
| **BO ≠ Rating divergence** | Factor_3, 8 increase BO but hurt ratings | Do A-list actors solve this? (drive BO but alienate critics) |
| **Composite R² = 19.4%** | 81% of success unexplained by factors | Does NLP (sentiment, keywords) capture that 10-15%? Do actor/director metrics? |
| **Ridge instability** | 40% of factors flip signs under regularization | Does adding actor/director data stabilize coefficients? Are factors overfitting on multicollinearity? |

---

## RECOMMENDATION: Phase 2 Priority Ranking

### 🔴 **CRITICAL (Do First)**
1. **Reverse Factor Analysis** — Without understanding what factors represent, recommendations cannot be operationalized
2. **Actor & Director Weight Analysis** — Highest business impact; answers "Is A-list talent worth it?"

### 🟠 **HIGH VALUE (Do Next)**
3. **NLP on Descriptions** — Could explain missing 10%+ of success variance; relatively easy to implement
4. **Key Moments/Mood Tagging** — Complements NLP; adds narrative dimension

### 🟡 **NICE-TO-HAVE (Do If Time)**
5. **Fill Missing Data** — Budget imputation and MPAA rating scraping improve sample completeness
6. **Explicit Hold-Out Test Set** — More rigorous validation; not required if CV is robust

---

## FILES AVAILABLE FOR NEXT PHASE

**Inputs:**
- [project_2_data_filled_with_api_with_efficiency.csv](project_2_data_filled_with_api_with_efficiency.csv) — Full dataset with factors
- [composite_scores.csv](composite_scores.csv) — Phase 1 success scores
- [PHASE1_MASTER_COEFFICIENT_TABLE.csv](PHASE1_MASTER_COEFFICIENT_TABLE.csv) — Baseline coefficients

**Outputs to Retain:**
- [PHASE1_SUMMARY.md](PHASE1_SUMMARY.md) — Document this summary as reference
- [baseline_models_results.csv](baseline_models_results.csv) — Control group predictions
- [ridge_summary.csv](ridge_summary.csv) — Ridge vs. OLS comparison (multicollinearity indicator)

**Next Phase Deliverables Should Include:**
- `PHASE2_ACTOR_DIRECTOR_ANALYSIS.md` + CSV results
- `PHASE2_NLP_SENTIMENT_ANALYSIS.md` + TF-IDF/keyword features
- `PHASE2_FACTOR_INTERPRETATION.md` + factor loadings table
- `PHASE2_REVISED_MASTER_TABLE.csv` — Updated coefficients with new features

---

## SUMMARY

**Your original vision is PARTIALLY realized in Phase 1:**

✅ **Done:**
- Composite score created (50-30-20 BO/Rating/ROI)
- Separate weights computed for each factor across three outcomes
- Control baselines established for comparison
- Commercial-critical tension identified

❌ **Not Done (Phase 2):**
- Reverse engineering the factors (still opaque)
- NLP on descriptions
- Actor/director salary and track record analysis
- Mood/narrative analysis
- Explicit hold-out test set

**The Phase 1 foundation is solid and enables all Phase 2 analyses. The most critical next step is decoding the factors—without that, even perfect predictions are not actionable.**

