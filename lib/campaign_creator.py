"""
Google Ads Campaign Creator (Standalone)
Creates restaurant campaigns via REST API following the campaign creation playbook.

All campaigns are created PAUSED. All operations follow the dry-run -> preview -> confirm pattern.

Usage:
    from lib.campaign_creator import CampaignCreator
    creator = CampaignCreator(
        client_name="Harborview Restaurant",
        account_id="1234567890",
        city="San Francisco",
        neighborhood="Embarcadero",
        cuisine="Chinese",
        website="https://harborviewrestaurant.com"
    )
    creator.verify_prerequisites()
    specs = creator.generate_campaign_spec(campaign_type="standard")
    for spec in specs:
        print(spec.to_preview())
    results = creator.execute_spec(specs, confirmed=True)
    audit = creator.post_creation_audit()
"""

import base64
import json
import os
import subprocess
import requests
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def get_access_token() -> str:
    """Get Google Cloud access token via gcloud CLI"""
    result = subprocess.run(
        ['gcloud', 'auth', 'application-default', 'print-access-token'],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


# ==================== DATA CLASSES ====================

@dataclass
class ImageAsset:
    """Validated image asset ready for upload"""
    file_path: str
    aspect_type: str  # landscape, square, portrait, logo
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    base64_data: str = ""
    resource_name: str = ""


@dataclass
class CampaignSpec:
    """Complete specification for a campaign, ready for execution"""
    client_name: str
    account_id: str
    campaign_name: str
    campaign_type: str
    budget_daily_usd: float
    bid_strategy: str
    geo_preset_key: str
    geo_target_constant_id: str
    radius_miles: int
    ad_schedule: Dict
    negative_keyword_lists: List[str]
    negative_keywords: List[Dict] = field(default_factory=list)
    keywords: List[Dict] = field(default_factory=list)
    headlines: List[str] = field(default_factory=list)
    descriptions: List[str] = field(default_factory=list)
    final_url: str = ""
    asset_groups: List[Dict] = field(default_factory=list)
    images: List[ImageAsset] = field(default_factory=list)
    created_resources: Dict = field(default_factory=dict)

    def to_preview(self) -> str:
        """Human-readable preview"""
        lines = [
            f"Campaign: {self.campaign_name}",
            f"  Type: {self.campaign_type}",
            f"  Budget: ${self.budget_daily_usd}/day",
            f"  Bid Strategy: {self.bid_strategy}",
            f"  Geo: {self.geo_preset_key} ({self.radius_miles}mi radius), PRESENCE only",
            f"  Schedule: {self.ad_schedule.get('start_hour', 10)}:00-{self.ad_schedule.get('end_hour', 22)}:00",
        ]
        if self.keywords:
            lines.append(f"  Keywords: {len(self.keywords)} (PHRASE match)")
            for kw in self.keywords[:5]:
                lines.append(f"    - \"{kw['text']}\"")
            if len(self.keywords) > 5:
                lines.append(f"    ... and {len(self.keywords) - 5} more")
        if self.headlines:
            lines.append(f"  Headlines: {len(self.headlines)}")
            for h in self.headlines[:3]:
                lines.append(f"    - \"{h}\" ({len(h)} chars)")
            if len(self.headlines) > 3:
                lines.append(f"    ... and {len(self.headlines) - 3} more")
        if self.descriptions:
            lines.append(f"  Descriptions: {len(self.descriptions)}")
        if self.asset_groups:
            lines.append(f"  Asset Groups: {len(self.asset_groups)}")
            for ag in self.asset_groups:
                lines.append(f"    - {ag['name']}: {len(ag.get('search_themes', []))} search themes")
        if self.images:
            lines.append(f"  Images: {len(self.images)}")
        lines.append(f"  Negative Keywords: {len(self.negative_keywords)}")
        lines.append(f"  Status: PAUSED (created paused for safety)")
        return "\n".join(lines)


# ==================== MAIN CLASS ====================

class CampaignCreator:
    """
    Create Google Ads campaigns for restaurant clients.

    Standalone version — pass client details directly instead of reading from clients.json.
    """

    API_VERSION = "v21"
    BASE_URL = f"https://googleads.googleapis.com/{API_VERSION}"

    def __init__(
        self,
        client_name: str,
        account_id: str,
        city: str,
        neighborhood: str = "",
        cuisine: str = "",
        website: str = "",
        config_path: str = None,
        image_dir: str = None,
    ):
        self.client_name = client_name
        self.account_id = account_id
        self.city = city
        self.neighborhood = neighborhood or ""
        self.cuisine = cuisine or ""
        self.website = website or ""
        self.image_dir = image_dir
        self._token = None
        self._created_resources = []

        # Find config directory
        base_dir = Path(__file__).parent.parent
        config_dir = Path(config_path) if config_path else base_dir / "config"
        templates_dir = base_dir / "templates"

        # Load config
        config_file = config_dir / "config.json"
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
        else:
            config = {}

        self.developer_token = config.get("google_ads", {}).get("developer_token", "")
        self.mcc_id = config.get("google_ads", {}).get("mcc_id", "")
        self.gcp_project = config.get("gcp_project", "")

        # Load preset files
        self.presets = self._load_json(config_dir / "campaign-presets.json")
        self.negatives = self._load_json(config_dir / "negative-keywords.json")
        self.keyword_seeds = self._load_json(config_dir / "keyword-seeds.json")
        self.copy_templates = self._load_json(templates_dir / "copy-templates.json")

        # Log directory
        self.log_dir = base_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_json(path: Path) -> Dict:
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    @property
    def token(self) -> str:
        if not self._token:
            self._token = get_access_token()
        return self._token

    def _get_headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "developer-token": self.developer_token,
            "x-goog-user-project": self.gcp_project,
            "Content-Type": "application/json",
            "login-customer-id": self.mcc_id,
        }

    def _api_request(self, url: str, method: str = "POST", payload: Dict = None) -> Tuple[bool, Dict]:
        try:
            if method == "POST":
                resp = requests.post(url, headers=self._get_headers(), json=payload)
            elif method == "GET":
                resp = requests.get(url, headers=self._get_headers())
            else:
                return False, {"error": f"Unsupported method: {method}"}
            if resp.status_code in [200, 201]:
                return True, resp.json() if resp.text else {}
            else:
                return False, {"error": resp.text, "status_code": resp.status_code}
        except Exception as e:
            return False, {"error": str(e)}

    def _search_api(self, query: str) -> Tuple[bool, List[Dict]]:
        url = f"{self.BASE_URL}/customers/{self.account_id}/googleAds:search"
        success, response = self._api_request(url, "POST", {"query": query})
        if success:
            return True, response.get("results", [])
        return False, response

    def _resolve_variables(self, text: str) -> str:
        replacements = {
            "{client_name}": self.client_name or "",
            "{city}": self.city or "",
            "{neighborhood}": self.neighborhood or "",
            "{cuisine}": self.cuisine or "",
        }
        result = text
        for var, val in replacements.items():
            result = result.replace(var, val)
        return result

    def _get_geo_preset(self) -> Tuple[Dict, str]:
        """Get geo preset by matching city name"""
        geo_presets = self.presets.get("geo_presets", {})
        city_lower = self.city.lower()
        for key, preset in geo_presets.items():
            if key.replace("_", " ") in city_lower or city_lower in preset.get("name", "").lower():
                return preset, key
        # Default to san_francisco
        return geo_presets.get("san_francisco", {}), "san_francisco"

    # ==================== PREREQUISITES ====================

    def verify_prerequisites(self) -> Dict:
        checks = []
        query = "SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1"
        success, results = self._search_api(query)
        checks.append({
            "check": "Google Ads account accessible",
            "passed": success,
            "detail": f"Account {self.account_id}" if success else "Cannot access account"
        })

        conv_query = """
            SELECT conversion_action.name, conversion_action.status,
                conversion_action.value_settings.default_value
            FROM conversion_action
            WHERE conversion_action.status = 'ENABLED'
        """
        success, conv_results = self._search_api(conv_query)
        if success:
            conv_names = [r.get("conversionAction", {}).get("name", "") for r in conv_results]
            for req in ["phone_call_click", "reservation_click", "directions_click"]:
                found = any(req.lower() in name.lower() for name in conv_names)
                checks.append({
                    "check": f"Conversion action: {req}",
                    "passed": found,
                    "detail": "Found" if found else "MISSING"
                })

            # Check PE form tracking
            has_pe_form = any("private_event" in n.lower() or "pe_form" in n.lower() for n in conv_names)
            checks.append({
                "check": "PE form tracking",
                "passed": has_pe_form,
                "detail": "Found" if has_pe_form else "WARNING: No PE form action — PE campaigns cannot track leads"
            })

            # Check conversion values non-zero
            pe_form_names = ["private_event_form", "pe_form_submit"]
            phone_names = ["phone_call_click", "phone_call"]
            for row in conv_results:
                action = row.get("conversionAction", {})
                name = action.get("name", "")
                default_val = action.get("valueSettings", {}).get("defaultValue", 0)
                is_pe = any(n in name.lower() for n in pe_form_names)
                is_phone = any(n in name.lower() for n in phone_names)
                if is_pe or is_phone:
                    has_value = default_val and float(default_val) > 0
                    checks.append({
                        "check": f"Conversion value: {name}",
                        "passed": has_value,
                        "detail": f"${default_val}" if has_value else "WARNING: $0 — run configure_pe_conversion_values()"
                    })

        checks.append({"check": "City", "passed": bool(self.city), "detail": self.city or "MISSING"})
        checks.append({"check": "Website", "passed": bool(self.website), "detail": self.website or "MISSING"})

        return {"passed": all(c["passed"] for c in checks), "checks": checks}

    # ==================== PE CONVERSION VALUES ====================

    def configure_pe_conversion_values(self, avg_event_value: float, avg_check: float) -> Dict:
        """
        Set conversion values on PE-relevant conversion actions.

        Args:
            avg_event_value: Average private event value (e.g., 5000)
            avg_check: Average dinner check (e.g., 85)

        Returns:
            Dict with 'updated' list and 'errors' list
        """
        if not avg_event_value:
            return {"updated": [], "errors": ["avg_event_value is required"]}

        pe_form_value = round(avg_event_value * 0.33, 2)
        phone_call_value = round(avg_check * 0.50, 2)

        query = """
            SELECT conversion_action.resource_name, conversion_action.name,
                conversion_action.value_settings.default_value
            FROM conversion_action WHERE conversion_action.status = 'ENABLED'
        """
        success, results = self._search_api(query)
        if not success:
            return {"updated": [], "errors": ["Failed to query conversion actions"]}

        pe_form_patterns = [
            "private event", "event form", "event inquiry", "event lead",
            "private dining", "wedding form", "wedding venue",
            "corporate event", "farm venue", "venue form",
            "catering form", "group form", "party form",
        ]
        pe_form_exclusions = ["quality visit", "scroll", "30 sec"]
        phone_patterns = [
            "click call", "calls from ads",
            "phone_number_click", "phone number click", "call click",
        ]
        unmodifiable_types = ["GOOGLE_HOSTED", "SMART_CAMPAIGN_AD_CLICKS_TO_CALL",
                              "SMART_CAMPAIGN_MAP_CLICKS_TO_CALL", "SMART_CAMPAIGN_MAP_DIRECTIONS",
                              "SMART_CAMPAIGN_TRACKED_CALLS", "STORE_VISITS"]
        updated, errors = [], []

        for row in results:
            action = row.get("conversionAction", {})
            name = action.get("name", "").lower()
            resource_name = action.get("resourceName", "")
            action_type = action.get("type", "")
            if action_type in unmodifiable_types:
                continue
            target_value = None
            is_pe_match = any(p in name for p in pe_form_patterns)
            is_excluded = any(e in name for e in pe_form_exclusions)
            if is_pe_match and not is_excluded:
                target_value = pe_form_value
            elif any(p in name for p in phone_patterns):
                target_value = phone_call_value
            if target_value is None:
                continue

            current_value = action.get("valueSettings", {}).get("defaultValue", 0)
            if current_value == target_value:
                updated.append({"name": action.get("name", ""), "value": target_value, "status": "already_set"})
                continue

            mutate_url = f"{self.BASE_URL}/customers/{self.account_id}/conversionActions:mutate"
            payload = {
                "operations": [{
                    "update": {
                        "resourceName": resource_name,
                        "valueSettings": {
                            "defaultValue": target_value,
                            "defaultCurrencyCode": "USD",
                            "alwaysUseDefaultValue": True
                        }
                    },
                    "updateMask": "valueSettings.defaultValue,valueSettings.defaultCurrencyCode,valueSettings.alwaysUseDefaultValue"
                }]
            }
            success, response = self._api_request(mutate_url, "POST", payload)
            if success:
                updated.append({"name": action.get("name", ""), "value": target_value, "previous_value": current_value, "status": "updated"})
            else:
                errors.append({"name": action.get("name", ""), "error": response.get("error", "Unknown error")})

        return {"pe_form_value": pe_form_value, "phone_call_value": phone_call_value, "updated": updated, "errors": errors}

    # ==================== NEGATIVE KEYWORDS ====================

    def _build_negative_list(self, campaign_type: str) -> List[Dict]:
        rules = self.negatives.get("application_rules", {})
        list_names = rules.get(campaign_type, ["base_restaurant"])
        keywords = []
        seen = set()

        for list_name in list_names:
            if list_name == "cuisine_exclusions":
                for exc_key, exc_data in self.negatives.get("cuisine_exclusions", {}).items():
                    if exc_key.startswith("_"):
                        continue
                    cuisine_name = exc_key.replace("not_", "")
                    if cuisine_name in self.cuisine.lower():
                        continue
                    match_type = exc_data.get("match_type", "PHRASE")
                    for kw in exc_data.get("keywords", []):
                        if kw not in seen:
                            keywords.append({"text": kw, "match_type": match_type})
                            seen.add(kw)
            else:
                data = self.negatives.get(list_name, {})
                match_type = data.get("match_type", "PHRASE")
                for kw in data.get("keywords", []):
                    if kw not in seen:
                        keywords.append({"text": kw, "match_type": match_type})
                        seen.add(kw)
        return keywords

    # ==================== KEYWORD GENERATION ====================

    def _generate_pe_keywords(self) -> List[Dict]:
        templates = self.keyword_seeds.get("pe_keywords", {}).get("templates", [])
        return [{"text": self._resolve_variables(t), "match_type": "PHRASE"}
                for t in templates if self._resolve_variables(t) and len(self._resolve_variables(t)) <= 80]

    def _generate_search_themes(self, campaign_type: str, asset_group_key: str = None) -> List[str]:
        if campaign_type == "foot_traffic_pmax":
            cuisine_lower = self.cuisine.lower()
            cuisine_map = {
                "mexican": "mexican", "chinese": "chinese", "italian": "italian",
                "japanese": "japanese", "american": "american", "french": "french",
                "sports bar": "sports_bar", "fine dining": "fine_dining",
                "hotel": "hotel_restaurant",
            }
            cuisine_key = next((v for k, v in cuisine_map.items() if k in cuisine_lower), "american")
            templates = self.keyword_seeds.get("foot_traffic_keywords_by_cuisine", {}).get(cuisine_key, [])
            return [self._resolve_variables(t) for t in templates[:8]]
        elif campaign_type == "pe_pmax":
            themes_config = self.presets.get("pmax_asset_group_themes", {}).get("private_events", {})
            if asset_group_key and asset_group_key in themes_config:
                return [self._resolve_variables(t) for t in themes_config[asset_group_key].get("search_themes", [])]
        return []

    # ==================== CREATIVE GENERATION ====================

    def _generate_headlines(self, campaign_type: str, max_count: int = 15) -> List[str]:
        templates = self.copy_templates.get(campaign_type, {}).get("headlines", [])
        tier_order = {"proven": 0, "promising": 1, "untested": 2}
        sorted_templates = sorted(templates, key=lambda t: tier_order.get(t.get("performance_tier", "untested"), 2))
        headlines = []
        for tmpl in sorted_templates[:max_count]:
            text = self._resolve_variables(tmpl["text"])
            if text and len(text) <= 30:
                headlines.append(text)
        return headlines[:max_count]

    def _generate_descriptions(self, campaign_type: str, max_count: int = 5) -> List[str]:
        templates = self.copy_templates.get(campaign_type, {}).get("descriptions", [])
        tier_order = {"proven": 0, "promising": 1, "untested": 2}
        sorted_templates = sorted(templates, key=lambda t: tier_order.get(t.get("performance_tier", "untested"), 2))
        descriptions = []
        for tmpl in sorted_templates[:max_count]:
            text = self._resolve_variables(tmpl["text"])
            if text and len(text) <= 90:
                descriptions.append(text)
        return descriptions[:max_count]

    def _generate_long_headlines(self, campaign_type: str, max_count: int = 5) -> List[str]:
        templates = self.copy_templates.get(campaign_type, {}).get("long_headlines", [])
        tier_order = {"proven": 0, "promising": 1, "untested": 2}
        sorted_templates = sorted(templates, key=lambda t: tier_order.get(t.get("performance_tier", "untested"), 2))
        headlines = []
        for tmpl in sorted_templates[:max_count]:
            text = self._resolve_variables(tmpl["text"])
            if text and len(text) <= 90:
                headlines.append(text)
        return headlines[:max_count]

    # ==================== IMAGE HANDLING ====================

    def _scan_images(self, image_dir: str = None) -> List[ImageAsset]:
        img_path = Path(image_dir or self.image_dir or "")
        if not img_path.exists():
            return []
        prefix_map = {"ls_": "landscape", "sq_": "square", "pt_": "portrait", "logo_sq_": "logo_square", "logo_": "logo"}
        assets = []
        for f in sorted(img_path.iterdir()):
            if f.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            if f.stat().st_size > 5 * 1024 * 1024:
                continue
            aspect_type = "landscape"
            for prefix, atype in prefix_map.items():
                if f.name.startswith(prefix):
                    aspect_type = atype
                    break
            assets.append(ImageAsset(file_path=str(f), aspect_type=aspect_type, size_bytes=f.stat().st_size))
        return assets

    def upload_image_assets(self, images: List[ImageAsset]) -> List[ImageAsset]:
        url = f"{self.BASE_URL}/customers/{self.account_id}/assets:mutate"
        uploaded = []
        for img in images:
            with open(img.file_path, "rb") as f:
                img.base64_data = base64.b64encode(f.read()).decode("utf-8")
            payload = {"operations": [{"create": {"name": f"{self.client_name} - {os.path.basename(img.file_path)}", "type": "IMAGE", "imageAsset": {"data": img.base64_data}}}]}
            success, response = self._api_request(url, "POST", payload)
            if success and response.get("results"):
                img.resource_name = response["results"][0].get("resourceName", "")
                self._created_resources.append({"type": "image_asset", "resource_name": img.resource_name})
            img.base64_data = ""
            uploaded.append(img)
        return uploaded

    def create_text_assets(self, texts: List[str], field_type: str = "HEADLINE") -> List[str]:
        url = f"{self.BASE_URL}/customers/{self.account_id}/assets:mutate"
        resource_names = []
        operations = [{"create": {"name": f"{self.client_name} - {t[:30]}", "type": "TEXT", "textAsset": {"text": t}}} for t in texts]
        for i in range(0, len(operations), 20):
            success, response = self._api_request(url, "POST", {"operations": operations[i:i+20]})
            if success:
                for r in response.get("results", []):
                    resource_names.append(r.get("resourceName", ""))
        return resource_names

    # ==================== CAMPAIGN CREATION ====================

    def _create_budget(self, name: str, daily_usd: float) -> Optional[str]:
        url = f"{self.BASE_URL}/customers/{self.account_id}/campaignBudgets:mutate"
        payload = {"operations": [{"create": {"name": f"{name} Budget - {datetime.now().strftime('%Y%m%d')}", "amountMicros": str(int(daily_usd * 1_000_000)), "deliveryMethod": "STANDARD", "explicitlyShared": False}}]}
        success, response = self._api_request(url, "POST", payload)
        if success:
            return response.get("results", [{}])[0].get("resourceName", "")
        return None

    def _create_search_campaign(self, spec: CampaignSpec) -> Optional[str]:
        budget_rn = self._create_budget(spec.campaign_name, spec.budget_daily_usd)
        if not budget_rn:
            return None
        url = f"{self.BASE_URL}/customers/{self.account_id}/campaigns:mutate"
        payload = {"operations": [{"create": {"name": spec.campaign_name, "advertisingChannelType": "SEARCH", "status": "PAUSED", "campaignBudget": budget_rn, "maximizeConversions": {}, "networkSettings": {"targetGoogleSearch": True, "targetSearchNetwork": False, "targetContentNetwork": False}, "geoTargetTypeSetting": {"positiveGeoTargetType": "PRESENCE", "negativeGeoTargetType": "PRESENCE_OR_INTEREST"}}}]}
        success, response = self._api_request(url, "POST", payload)
        if not success:
            return None
        campaign_rn = response.get("results", [{}])[0].get("resourceName", "")
        campaign_id = campaign_rn.split("/")[-1]
        spec.created_resources["campaign"] = campaign_rn
        spec.created_resources["campaign_id"] = campaign_id
        self._set_location_targeting(campaign_id, spec.geo_target_constant_id)
        self._set_ad_schedule(campaign_id, spec.ad_schedule)
        self._apply_negatives(campaign_id, spec.negative_keywords)
        return campaign_rn

    def _create_pmax_campaign(self, spec: CampaignSpec) -> Optional[str]:
        budget_rn = self._create_budget(spec.campaign_name, spec.budget_daily_usd)
        if not budget_rn:
            return None
        url = f"{self.BASE_URL}/customers/{self.account_id}/campaigns:mutate"
        payload = {"operations": [{"create": {"name": spec.campaign_name, "advertisingChannelType": "PERFORMANCE_MAX", "status": "PAUSED", "campaignBudget": budget_rn, "maximizeConversions": {}, "geoTargetTypeSetting": {"positiveGeoTargetType": "PRESENCE", "negativeGeoTargetType": "PRESENCE_OR_INTEREST"}}}]}
        success, response = self._api_request(url, "POST", payload)
        if not success:
            return None
        campaign_rn = response.get("results", [{}])[0].get("resourceName", "")
        campaign_id = campaign_rn.split("/")[-1]
        spec.created_resources["campaign"] = campaign_rn
        spec.created_resources["campaign_id"] = campaign_id
        self._set_location_targeting(campaign_id, spec.geo_target_constant_id)
        self._set_ad_schedule(campaign_id, spec.ad_schedule)
        return campaign_rn

    def _create_ad_group(self, campaign_rn: str, name: str) -> Optional[str]:
        url = f"{self.BASE_URL}/customers/{self.account_id}/adGroups:mutate"
        payload = {"operations": [{"create": {"name": name, "campaign": campaign_rn, "status": "ENABLED", "type": "SEARCH_STANDARD"}}]}
        success, response = self._api_request(url, "POST", payload)
        if success:
            return response.get("results", [{}])[0].get("resourceName", "")
        return None

    def _add_keywords(self, ad_group_rn: str, keywords: List[Dict]) -> int:
        url = f"{self.BASE_URL}/customers/{self.account_id}/adGroupCriteria:mutate"
        operations = [{"create": {"adGroup": ad_group_rn, "status": "ENABLED", "keyword": {"text": kw["text"], "matchType": kw.get("match_type", "PHRASE")}}} for kw in keywords]
        added = 0
        for i in range(0, len(operations), 50):
            success, response = self._api_request(url, "POST", {"operations": operations[i:i+50]})
            if success:
                added += len(response.get("results", []))
        return added

    def _create_rsa(self, ad_group_rn: str, headlines: List[str], descriptions: List[str], final_url: str) -> Optional[str]:
        url = f"{self.BASE_URL}/customers/{self.account_id}/adGroupAds:mutate"
        payload = {"operations": [{"create": {"adGroup": ad_group_rn, "status": "ENABLED", "ad": {"responsiveSearchAd": {"headlines": [{"text": h} for h in headlines[:15]], "descriptions": [{"text": d} for d in descriptions[:4]]}, "finalUrls": [final_url]}}}]}
        success, response = self._api_request(url, "POST", payload)
        if success:
            return response.get("results", [{}])[0].get("resourceName", "")
        return None

    def _create_audience(self, name: str, in_market_audiences: List[Dict]) -> Optional[str]:
        """Create an Audience resource with in-market segments. Returns resource name."""
        segments = []
        for aud in in_market_audiences:
            aud_id = aud.get("id", "")
            if aud_id:
                segments.append({
                    "userInterest": {
                        "userInterestCategory": f"customers/{self.account_id}/userInterests/{aud_id}"
                    }
                })
        if not segments:
            return None
        url = f"{self.BASE_URL}/customers/{self.account_id}/audiences:mutate"
        payload = {
            "operations": [{
                "create": {
                    "name": name,
                    "description": "PE audience signal — in-market event planning segments",
                    "dimensions": [{
                        "audienceSegments": {
                            "segments": segments
                        }
                    }]
                }
            }]
        }
        success, response = self._api_request(url, "POST", payload)
        if success:
            rn = response.get("results", [{}])[0].get("resourceName", "")
            self._created_resources.append({"type": "audience", "resource_name": rn, "name": name})
            return rn
        print(f"WARNING: Failed to create audience '{name}': {response.get('error', '')}")
        return None

    def build_asset_group(self, campaign_rn: str, group_config: Dict, headline_rns: List[str], description_rns: List[str], long_headline_rns: List[str], image_rns: Dict, audience_signals: Dict = None) -> Optional[str]:
        url = f"{self.BASE_URL}/customers/{self.account_id}/googleAds:mutate"
        ag_temp_id = "-1"
        operations = [
            {"assetGroupOperation": {"create": {"resourceName": f"customers/{self.account_id}/assetGroups/{ag_temp_id}", "name": group_config["name"], "campaign": campaign_rn, "status": "ENABLED"}}},
            {"assetGroupListingGroupFilterOperation": {"create": {"assetGroup": f"customers/{self.account_id}/assetGroups/{ag_temp_id}", "type": "UNIT_INCLUDED", "listingSource": "WEBPAGE"}}},
        ]
        for rn in headline_rns[:15]:
            operations.append({"assetGroupAssetOperation": {"create": {"assetGroup": f"customers/{self.account_id}/assetGroups/{ag_temp_id}", "asset": rn, "fieldType": "HEADLINE"}}})
        for rn in long_headline_rns[:5]:
            operations.append({"assetGroupAssetOperation": {"create": {"assetGroup": f"customers/{self.account_id}/assetGroups/{ag_temp_id}", "asset": rn, "fieldType": "LONG_HEADLINE"}}})
        for rn in description_rns[:5]:
            operations.append({"assetGroupAssetOperation": {"create": {"assetGroup": f"customers/{self.account_id}/assetGroups/{ag_temp_id}", "asset": rn, "fieldType": "DESCRIPTION"}}})
        field_type_map = {"landscape": "MARKETING_IMAGE", "square": "SQUARE_MARKETING_IMAGE", "portrait": "PORTRAIT_MARKETING_IMAGE", "logo": "LOGO", "logo_square": "LOGO"}
        for aspect_type, rns in image_rns.items():
            ft = field_type_map.get(aspect_type, "MARKETING_IMAGE")
            for rn in rns:
                operations.append({"assetGroupAssetOperation": {"create": {"assetGroup": f"customers/{self.account_id}/assetGroups/{ag_temp_id}", "asset": rn, "fieldType": ft}}})
        for theme in group_config.get("search_themes", [])[:25]:
            operations.append({"assetGroupSignalOperation": {"create": {"assetGroup": f"customers/{self.account_id}/assetGroups/{ag_temp_id}", "searchTheme": {"text": theme}}}})

        # Audience signals (for PE PMax)
        # Requires creating an Audience resource first, then referencing it
        if audience_signals and audience_signals.get("in_market_audiences"):
            audience_rn = self._create_audience(
                name=f"{group_config['name']} - PE Audience Signal",
                in_market_audiences=audience_signals["in_market_audiences"]
            )
            if audience_rn:
                operations.append({
                    "assetGroupSignalOperation": {
                        "create": {
                            "assetGroup": f"customers/{self.account_id}/assetGroups/{ag_temp_id}",
                            "audience": {
                                "audience": audience_rn
                            }
                        }
                    }
                })

        success, response = self._api_request(url, "POST", {"mutateOperations": operations})
        if success:
            results = response.get("mutateOperationResponses", [])
            if results:
                return results[0].get("assetGroupResult", {}).get("resourceName", "")
        return None

    # ==================== SETTINGS ====================

    def _set_location_targeting(self, campaign_id: str, geo_target_constant_id: str) -> bool:
        url = f"{self.BASE_URL}/customers/{self.account_id}/campaignCriteria:mutate"
        payload = {"operations": [{"create": {"campaign": f"customers/{self.account_id}/campaigns/{campaign_id}", "location": {"geoTargetConstant": f"geoTargetConstants/{geo_target_constant_id}"}}}]}
        success, _ = self._api_request(url, "POST", payload)
        return success

    def _set_ad_schedule(self, campaign_id: str, schedule: Dict) -> bool:
        days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
        url = f"{self.BASE_URL}/customers/{self.account_id}/campaignCriteria:mutate"
        operations = [{"create": {"campaign": f"customers/{self.account_id}/campaigns/{campaign_id}", "adSchedule": {"dayOfWeek": day, "startHour": schedule.get("start_hour", 10), "startMinute": "ZERO", "endHour": schedule.get("end_hour", 22), "endMinute": "ZERO"}}} for day in days]
        success, _ = self._api_request(url, "POST", {"operations": operations})
        return success

    def _apply_negatives(self, campaign_id: str, negatives: List[Dict]) -> int:
        url = f"{self.BASE_URL}/customers/{self.account_id}/campaignCriteria:mutate"
        operations = [{"create": {"campaign": f"customers/{self.account_id}/campaigns/{campaign_id}", "negative": True, "keyword": {"text": n["text"], "matchType": n.get("match_type", "PHRASE")}}} for n in negatives]
        added = 0
        for i in range(0, len(operations), 50):
            success, response = self._api_request(url, "POST", {"operations": operations[i:i+50]})
            if success:
                added += len(response.get("results", []))
        return added

    # ==================== SPEC GENERATION ====================

    def generate_campaign_spec(self, campaign_type: str = "standard") -> List[CampaignSpec]:
        packages = self.presets.get("campaign_packages", {})
        budget_defaults = self.presets.get("budget_defaults", {})
        schedule = self.presets.get("ad_schedule", {}).get("default", {})
        geo_preset, geo_key = self._get_geo_preset()

        campaign_types = packages.get(campaign_type, {}).get("campaigns", [campaign_type])
        specs = []

        for ctype in campaign_types:
            budget = budget_defaults.get(ctype, {})
            type_label_map = {"foot_traffic_pmax": "PMAX", "pe_search": "Private Events", "pe_pmax": "PE PMAX", "specialty": "Specialty"}
            campaign_name = f"Jay St. | {self.client_name} {type_label_map.get(ctype, ctype)}"
            negatives = self._build_negative_list(ctype)

            spec = CampaignSpec(
                client_name=self.client_name, account_id=self.account_id,
                campaign_name=campaign_name, campaign_type=ctype,
                budget_daily_usd=budget.get("recommended_daily_usd", 10),
                bid_strategy="MAXIMIZE_CONVERSIONS",
                geo_preset_key=geo_key,
                geo_target_constant_id=geo_preset.get("geo_target_constant_id", ""),
                radius_miles=geo_preset.get("radius_miles", 15),
                ad_schedule=schedule,
                negative_keyword_lists=self.negatives.get("application_rules", {}).get(ctype, []),
                negative_keywords=negatives,
            )

            if ctype == "pe_search":
                spec.keywords = self._generate_pe_keywords()
                spec.headlines = self._generate_headlines("pe_search", 15)
                spec.descriptions = self._generate_descriptions("pe_search", 4)
                spec.final_url = self.website or f"https://{self.client_name.lower().replace(' ', '')}.com"
            elif ctype in ("foot_traffic_pmax", "pe_pmax"):
                themes_key = "foot_traffic" if ctype == "foot_traffic_pmax" else "private_events"
                themes_config = self.presets.get("pmax_asset_group_themes", {}).get(themes_key, {})
                for ag_key, ag_config in themes_config.items():
                    if ag_key.startswith("_"):
                        continue
                    if not ag_config.get("required", False):
                        if ag_key == "sports_entertainment" and "sports" not in self.cuisine.lower():
                            continue
                        if ag_key == "spanish_language" and "mexican" not in self.cuisine.lower():
                            continue
                        if ag_key == "happy_hour" and "fine dining" in self.cuisine.lower():
                            continue
                        if ag_key == "wedding_rehearsal":
                            continue
                    search_themes = [self._resolve_variables(t) for t in ag_config.get("search_themes", [])]
                    spec.asset_groups.append({"key": ag_key, "name": self._resolve_variables(ag_config.get("name", ag_key)), "search_themes": search_themes})
                spec.headlines = self._generate_headlines(ctype, 15)
                spec.descriptions = self._generate_descriptions(ctype, 5)
                spec.images = self._scan_images()

            specs.append(spec)
        return specs

    # ==================== EXECUTION ====================

    def execute_spec(self, specs: List[CampaignSpec], confirmed: bool = False) -> Dict:
        if not confirmed:
            return {"status": "preview_only", "preview": "\n\n".join(s.to_preview() for s in specs)}

        results = []
        for spec in specs:
            result = {"campaign_name": spec.campaign_name, "type": spec.campaign_type}
            try:
                if spec.campaign_type == "pe_search":
                    campaign_rn = self._create_search_campaign(spec)
                    if campaign_rn:
                        ag_rn = self._create_ad_group(campaign_rn, f"{spec.campaign_name} - Keywords")
                        if ag_rn:
                            result["keywords_added"] = self._add_keywords(ag_rn, spec.keywords)
                            result["rsa_created"] = bool(self._create_rsa(ag_rn, spec.headlines, spec.descriptions, spec.final_url))
                        result["success"] = True
                        result["campaign_resource"] = campaign_rn
                    else:
                        result["success"] = False
                elif spec.campaign_type in ("foot_traffic_pmax", "pe_pmax"):
                    campaign_rn = self._create_pmax_campaign(spec)
                    if campaign_rn:
                        if spec.images:
                            spec.images = self.upload_image_assets(spec.images)
                        headline_rns = self.create_text_assets(spec.headlines, "HEADLINE")
                        long_headline_rns = self.create_text_assets(self._generate_long_headlines(spec.campaign_type), "LONG_HEADLINE")
                        desc_rns = self.create_text_assets(spec.descriptions, "DESCRIPTION")
                        image_rns = {}
                        for img in spec.images:
                            if img.resource_name:
                                image_rns.setdefault(img.aspect_type, []).append(img.resource_name)
                        audience_signals = self.presets.get("pe_pmax_audience_signals") if spec.campaign_type == "pe_pmax" else None
                        ag_count = sum(1 for ag in spec.asset_groups if self.build_asset_group(campaign_rn, ag, headline_rns, desc_rns, long_headline_rns, image_rns, audience_signals))
                        self._apply_negatives(spec.created_resources.get("campaign_id", ""), spec.negative_keywords)
                        result["success"] = True
                        result["campaign_resource"] = campaign_rn
                        result["asset_groups_created"] = ag_count
                    else:
                        result["success"] = False
            except Exception as e:
                result["success"] = False
                result["error"] = str(e)
            results.append(result)

        self._save_log(results)
        return {"status": "executed", "results": results}

    # ==================== AUDIT ====================

    def post_creation_audit(self) -> Dict:
        query = """
            SELECT campaign.id, campaign.name, campaign.status,
                campaign.geo_target_type_setting.positive_geo_target_type
            FROM campaign WHERE campaign.name LIKE 'Jay St.%' AND campaign.status = 'PAUSED'
            ORDER BY campaign.id DESC LIMIT 10
        """
        success, results = self._search_api(query)
        if not success:
            return {"passed": False, "error": "Failed to query campaigns"}
        audits = []
        for row in results:
            campaign = row.get("campaign", {})
            checks = [
                {"check": "PAUSED", "passed": campaign.get("status") == "PAUSED"},
                {"check": "PRESENCE targeting", "passed": campaign.get("geoTargetTypeSetting", {}).get("positiveGeoTargetType") in ("PRESENCE", "SEARCH_OR_PRESENCE", None)},
            ]
            audits.append({"campaign": campaign.get("name", ""), "checks": checks, "all_passed": all(c["passed"] for c in checks)})
        return {"passed": all(a["all_passed"] for a in audits), "campaigns": audits}

    def _save_log(self, results: List[Dict]):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"campaign_creation_{timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump({"timestamp": timestamp, "client_name": self.client_name, "account_id": self.account_id, "results": results}, f, indent=2)
