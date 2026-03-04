# Google Ads Campaign Creator

Create Google Ads campaigns for restaurant clients via the REST API. Handles foot traffic Performance Max, Private Events Search, PE PMax, and specialty campaigns with full safety guardrails.

Built by [Jay Street Media](https://jaystreetmedia.com) from learnings across 36+ restaurant marketing clients.

## Features

- **Full API campaign creation** — campaigns, budgets, keywords, RSAs, PMax asset groups, image uploads, audience signals
- **Template-driven** — keyword seeds, copy formulas, and negative keyword lists customizable per client
- **Performance intelligence** — tracks what works across your portfolio, prioritizes proven templates
- **Safety first** — all campaigns created PAUSED, dry-run previews, mutation logging
- **Restaurant-optimized** — PE keyword strategy, cuisine-specific targeting, ad schedules for dining hours

## Quick Start

```bash
# Clone
git clone https://github.com/farchionej/google-ads-campaign-creator.git
cd google-ads-campaign-creator

# Install dependencies
pip install requests

# Configure
cp config/config.example.json config/config.json
# Edit config.json with your Google Ads MCC ID, developer token, and GCP project

# Create campaigns
python3 -c "
from lib.campaign_creator import CampaignCreator
creator = CampaignCreator(
    client_name='My Restaurant',
    account_id='1234567890',
    city='San Francisco',
    neighborhood='Mission',
    cuisine='Mexican',
    website='https://myrestaurant.com'
)

# Generate and preview
specs = creator.generate_campaign_spec('standard')
for spec in specs:
    print(spec.to_preview())

# Execute (after reviewing)
# results = creator.execute_spec(specs, confirmed=True)
"
```

## Campaign Packages

| Package | Campaigns | Monthly Budget |
|---------|-----------|---------------|
| **Standard** | Foot Traffic PMax + PE Search | ~$900 |
| **Expanded** | + PE PMax (after 30 days) | ~$1,350 |
| **Full** | + Specialty (breakfast, happy hour) | ~$1,650 |

## What's Included

```
config/
  campaign-presets.json       # Naming, geo, schedules, budgets, bid strategies
  negative-keywords.json      # Base restaurant, PE-specific, cuisine exclusions
  keyword-seeds.json          # PE keyword templates, foot traffic by cuisine, RSA templates
templates/
  copy-templates.json         # Headline/description formulas with performance tiers
  IMAGE_GUIDE.md              # Image prep reference (dimensions, naming, workflow)
  performance-intelligence.json  # Cross-portfolio learning layer
lib/
  campaign_creator.py         # Core CampaignCreator class
docs/
  PLAYBOOK.md                 # Comprehensive campaign creation reference
  AGENT.md                    # Claude Code agent definition (if using with Claude)
examples/
  brief.json                  # Example per-client creative brief
```

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Location targeting | **PRESENCE only** | Area-of-interest wasted 28% of spend on out-of-area users |
| PE keyword match | **PHRASE** (not exact) | Exact match got zero clicks in 54 days; phrase converts |
| Negative keywords | **Applied before launch** | Every campaign without day-1 negatives accumulates waste |
| All campaigns | **Created PAUSED** | Safety — review before enabling |
| PE PMax timing | **After 30 days of Search** | Search proves intent before PMax casts wider net |
| PMax asset groups | **Single bulk mutate** | API requires AssetGroup + Assets together |

## Configuration

### Google Ads API Setup

1. [Google Ads API access](https://developers.google.com/google-ads/api/docs/get-started/introduction) with a developer token
2. GCP project with Google Ads API enabled
3. `gcloud auth application-default login` for authentication

### config.json

```json
{
  "gcp_project": "your-gcp-project-id",
  "google_ads": {
    "developer_token": "your-developer-token",
    "mcc_id": "your-mcc-id"
  }
}
```

## Usage with Claude Code

This framework includes a Claude Code agent definition (`docs/AGENT.md`) and skill command. If you use Claude Code:

1. Copy `docs/AGENT.md` to `.claude/agents/google-ads-campaign-creator.md`
2. Copy the skill command to `~/.claude/commands/google-ads-create.md`
3. Use `/google-ads-create [client_name]` to create campaigns interactively

## License

MIT

## Credits

Built by Jay Street Media. Learnings encoded from the Underdogs Tres + Cantina campaign audit (Tres: $1,056 wasted on 0 PE leads; Cantina: 25 PE leads generating ~$92K revenue from the same market).
