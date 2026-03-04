# Google Ads Campaign Creation Playbook

**Version**: 1.0 | **Last Updated**: March 2026 | **Author**: Jay Street Media

The reference document for launching Google Ads campaigns for restaurant clients. Encodes all learnings from portfolio audits (Underdogs Tres, Underdogs Cantina) into a repeatable system.

---

## Prerequisites

Before creating any campaigns, verify:

1. **Tracking onboarded**: GA4 + GTM + Google Ads account exist and are linked (via `/tracking-onboard`)
2. **Conversion actions verified**: `phone_call_click`, `reservation_click`, `directions_click` exist. For PE: `private_event_form` exists.
3. **PE landing page exists** (if running PE campaigns): Client website has a private events page with a form
4. **Client profile complete** in `clients.json`: `cuisine`, `city`, `neighborhood`, `avg_event_value`, `website`
5. **Image assets ready**: At minimum 1 landscape + 1 square + 1 logo in `clients/{key}/assets/google-ads/images/`

Run `verify_prerequisites(client_key)` to check all of the above programmatically.

---

## Campaign Architecture

### Standard Package (most restaurants)
| Campaign | Type | Budget | Purpose |
|----------|------|--------|---------|
| Foot Traffic PMax | PERFORMANCE_MAX | $10/day | Drive reservations, calls, directions |
| PE Search | SEARCH | $20/day | Capture private event intent |

**Monthly budget**: ~$900

### Expanded Package (add after 30 days)
| Campaign | Type | Budget | Purpose |
|----------|------|--------|---------|
| Foot Traffic PMax | PERFORMANCE_MAX | $10/day | Drive reservations, calls, directions |
| PE Search | SEARCH | $20/day | Capture private event intent |
| PE PMax | PERFORMANCE_MAX | $15/day | Broader PE funnel coverage |

**Monthly budget**: ~$1,350

### Full Package
All of the above + a specialty campaign (Breakfast, Happy Hour, Sports, etc.) at $10/day.

---

## Non-Negotiable Settings

These apply to **every** campaign. No exceptions.

### 1. Location Targeting: PRESENCE ONLY
```
positiveGeoTargetType = PRESENCE
```
**Why**: Tres wasted $1,056 (28% of total spend) on out-of-area users because of "area of interest" targeting. A user in New York googling "san francisco restaurants" doesn't walk in.

### 2. Phrase Match for PE Keywords (never exact)
Tres added 15 exact-match PE keywords → zero clicks in 54 days. Cantina converts on phrase match. Phrase match captures variations we can't predict.

### 3. Base Negative Keywords at Launch
Apply base negatives BEFORE enabling the campaign. Every campaign without day-1 negatives accumulates wasted spend in the first 2 weeks.

Negative lists: `.claude/shared/google-ads-negative-keywords.json`

### 4. Ad Schedule: 10AM-10PM
Restaurants don't convert at 3AM. Default schedule prevents overnight waste.

### 5. All Campaigns Created PAUSED
Safety pattern — user reviews and enables manually.

### 6. 3-5 Asset Groups per PMax Campaign
Minimum 3 for adequate signal diversity. Maximum 5 to avoid dilution.

---

## PE Search Setup

### Keyword Strategy
- Use PHRASE match templates from `google-ads-keyword-seeds.json`
- Customize with client's {city} and {neighborhood}
- Start with ~20 keywords, expand based on Search Terms Report
- Avoid broad match for PE (too much irrelevant traffic)

### RSA Requirements
- **15 headlines** (30 char max each). Use templates from `copy-templates.json`
- **4 descriptions** (90 char max each)
- Pin brand name headline to position 1
- Include {city} in at least 3 headlines for local relevance

### Negative Keywords
Apply both `base_restaurant` AND `pe_campaign_specific` lists from day 1.

### Monitoring
- **Week 1-2**: Check Search Terms Report daily. Add negatives for irrelevant terms.
- **Week 3-4**: Review impression share. If <50%, increase budget or broaden keywords.
- **Month 2+**: Monthly search terms review. Track Quality Score trends.

---

## Foot Traffic PMax Setup

### Asset Group Themes
Default 3 asset groups for most restaurants:
1. **General Food** (required) — Cuisine-specific search themes
2. **Happy Hour** (if applicable) — Drinks and social themes
3. **Neighborhood** — Location-based discovery themes

Sports bars add a 4th: **Sports & Entertainment**.
Mexican restaurants add: **Spanish-Language**.

### Search Themes
Use templates from `google-ads-keyword-seeds.json` → `foot_traffic_keywords_by_cuisine`.
Customize `{cuisine}`, `{city}`, `{neighborhood}` from client profile.

### Image Assets
Each asset group needs:
- Minimum: 1 landscape (1.91:1) + 1 square (1:1) + 1 logo
- Recommended: 3 landscape + 3 square + 1 portrait + 1 logo

See `IMAGE_GUIDE.md` for dimensions and naming conventions.

### Store Visit Goals
Enable if client has a physical location connected in Google Business Profile.

---

## PE PMax Setup (Phase 2)

**Launch criteria**: PE Search campaign has been active 30+ days with 15+ conversions.

### Why Wait
PE PMax is broader than Search. Without Search data to establish baseline intent, PMax casts too wide a net and bleeds budget into non-PE queries. Cantina data shows both formats capture different funnel stages, but Search proves intent first.

### Audience Signals (CRITICAL)
Without audience signals, PE PMax leaks 30%+ of impressions to general food queries.

Required signals:
- **Custom segments**: Event venue searches, competitor URLs (peerspace.com, theknot.com)
- **In-market audiences (API-available, 4 segments)**:
  - Event Planning Services (ID: 80512)
  - Corporate Event Planning (ID: 80521)
  - Party Supplies & Planning (ID: 80504)
  - Wedding Planning (ID: 80404)
- **In-market: other (UI-only, add manually in Google Ads)**:
  - Event Venues, Event Planners, Party Event Planners
  - Event Planning Programs, Event Coordinator
  - Party Planning, Corporate Events and Activities Ideas
- **Demographics**: Age 25-65, top 50% household income

### Asset Group Themes
- **Corporate/Team Building** — Business event search themes
- **Birthday/Celebration** — Personal celebration themes
- **Private Dining** — General private dining themes
- **Wedding/Rehearsal** (optional) — Only for venues that host weddings

---

## Budget & Bidding Guidelines

### Launch Phase (Days 1-30)
- Bid strategy: **Maximize Conversions** (no target CPA)
- Let the system learn. Don't touch budgets for 2 weeks minimum.
- Expected: Higher CPC, lower efficiency. This is normal.

### Optimization Phase (Day 30+)
- If 15+ conversions: Switch to **Target CPA**
- Set target CPA at 120% of actual CPA from first 30 days
- PE Search: $50-100/lead is acceptable for $3K+ events
- Foot traffic: Target 2-3x ROAS based on avg check value

### Budget Scaling
- Increase by max 20% per week
- Only scale campaigns with CPA below target
- Never scale PE PMax faster than PE Search

---

## Known Pitfalls (from Underdogs Audit)

| Pitfall | What Happened | Cost | Prevention |
|---------|--------------|------|------------|
| Area of interest targeting | Tres showed ads to out-of-area users | $1,056 (28%) | PRESENCE only — enforced in presets |
| Exact match PE keywords | 15 keywords → 0 clicks in 54 days | 54 days of zero PE traffic | PHRASE match only |
| No negative keywords | 99.6% of Tres PE impressions on non-PE terms | ~$1,000/month wasted | Base negatives at launch |
| No ad schedule | Spend during non-converting hours (midnight-8AM) | ~10-15% waste | 10AM-10PM default |
| PE PMax without signals | 30% of impressions leaked to food queries | ~30% of PE PMax budget | Audience signals required |
| Launching PE PMax too early | No baseline data for optimization | Inefficient spend | Wait for 30 days of Search data |

---

## Review Cadence

| Period | Action | Focus |
|--------|--------|-------|
| Daily (Week 1-2) | Search Terms Report review | Add negatives for irrelevant terms |
| Weekly (Month 1) | Performance check | CPC, CTR, conversion trends |
| Monthly (Ongoing) | Full audit via `/google-ads` | Budget efficiency, keyword QS, asset performance |
| Quarterly | Strategic review | Campaign package evaluation, PE PMax launch decision |

---

## Workflow Summary

```
1. /tracking-onboard {client}     ← Accounts + conversion actions
2. Prepare image assets            ← Drop in clients/{key}/assets/google-ads/images/
3. /google-ads-create {client}     ← Campaign creation (this playbook)
4. Review created campaigns        ← All PAUSED, verify settings
5. Enable campaigns                ← User approval
6. Monitor daily for 2 weeks       ← Search terms + negatives
7. Monthly audits via /google-ads  ← Ongoing optimization
```

---

## Reference Files

| File | Purpose |
|------|---------|
| `.claude/shared/google-ads-campaign-presets.json` | Campaign settings, geo, schedules, budgets |
| `.claude/shared/google-ads-negative-keywords.json` | Negative keyword seed lists |
| `.claude/shared/google-ads-keyword-seeds.json` | PE keyword templates, RSA templates |
| `.claude/shared/google-ads-creative/copy-templates.json` | Headline/description formulas |
| `.claude/shared/google-ads-creative/IMAGE_GUIDE.md` | Image prep guide |
| `.claude/shared/google-ads-creative/performance-intelligence.json` | Template performance tracking |
| `lib/google_ads_campaign_creator.py` | Campaign creation API library |
| `.claude/agents/google-ads-campaign-creator.md` | Agent definition |
