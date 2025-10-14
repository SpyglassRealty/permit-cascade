# main.py
# FastAPI service your OpenAI Agent will call as a custom Action.
# Features:
# - Address -> city/county via Nominatim (OpenStreetMap)
# - Cascading adapters: Austin first, then other cities/counties in Travis, Williamson, Hays, Harris
# - Normalized response format
# - For portals without a clean public API: returns "manual_check_url" you (or the Agent) can surface.

from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
import urllib.parse
import time

app = FastAPI(title="Permit Search Cascade", version="1.0.0")

# ---------- Data models ----------

class Permit(BaseModel):
    jurisdiction: str
    portal: str
    permit_id: Optional[str] = None
    address: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    issued_date: Optional[str] = None
    link: Optional[str] = None
    manual_check_url: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

class SearchResponse(BaseModel):
    address_input: str
    resolved_city: Optional[str]
    resolved_county: Optional[str]
    hits: List[Permit]
    checked: List[str]  # list of adapter names tried, in order

# ---------- Helpers ----------

USER_AGENT = "Spyglass-PermitBot/1.0 (+https://spyglassrealty.com)"
HTTP_TIMEOUT = 30.0

def http_client():
    return httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})

def geocode_nominatim(addr: str) -> Dict[str, Optional[str]]:
    \"\"\"Geocode with Nominatim (no API key). Returns city + county when possible.\"\"\"
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": addr, "format": "json", "addressdetails": 1, "limit": 1}
    with http_client() as s:
        r = s.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    if not data:
        return {"city": None, "county": None}
    comp = data[0].get("address", {})
    # Prefer city/town/village; county is usually "<Name> County"
    city = comp.get("city") or comp.get("town") or comp.get("village") or comp.get("municipality") or comp.get("hamlet")
    county = comp.get("county")
    return {"city": city, "county": county}

def norm(s: Optional[str]) -> Optional[str]:
    return s.strip() if s else s

# ---------- Adapters (lightweight, extendable) ----------

class BaseAdapter:
    name: str
    def search(self, address: str, city: Optional[str], county: Optional[str]) -> List[Permit]:
        raise NotImplementedError

# 1) City of Austin (re-use your current logic if you have it).
# Here we keep a placeholder that always returns [].
# If you have working Austin code, paste it inside this adapter and return Permit[].
class AustinAdapter(BaseAdapter):
    name = "City of Austin (AB+C)"
    portal = "Austin Build + Connect"
    def search(self, address: str, city: Optional[str], county: Optional[str]) -> List[Permit]:
        # TODO: Replace this with your existing Austin scraping/call.
        # Example of a real item to return once wired:
        # return [Permit(jurisdiction="City of Austin", portal=self.portal, permit_id="PR-2024-12345", address=address, type="Building", status="Issued", issued_date="2024-10-01", link="https://...")]
        return []

# 2) Generic “manual” adapter that provides a search page the agent/user can click.
# Use when there is no reliable public API.
class ManualPortalAdapter(BaseAdapter):
    def __init__(self, name: str, portal: str, search_url_template: str):
        self.name = name
        self.portal = portal
        self.search_url_template = search_url_template

    def search(self, address: str, city: Optional[str], county: Optional[str]) -> List[Permit]:
        # Many portals support simple “open search page”; some accept query params; we at least return the entry page.
        # We'll always return a "manual_check_url" item so the Agent can present it.
        url = self.search_url_template.format(
            q=urllib.parse.quote_plus(address)
        )
        return [Permit(
            jurisdiction=self.name,
            portal=self.portal,
            manual_check_url=url
        )]

# 3) Example Tyler CSS read-only adapter “stub” -> uses Manual link for now.
class TylerCssAdapter(ManualPortalAdapter):
    pass

# 4) Example MyGovernmentOnline (MGO) stub -> manual link now.
class MgoAdapter(ManualPortalAdapter):
    pass

# 5) County-level “manual” stubs
class CountyAdapter(ManualPortalAdapter):
    pass

# ---------- Registry & routing ----------

# We’ll keep a single list in the **order** we want to try.
# City of Austin first; then cities in Travis/WilCo/Hays; then Harris/Houston.
ADAPTERS_IN_ORDER: List[BaseAdapter] = [
    AustinAdapter(),

    # Travis County & nearby cities
    TylerCssAdapter("City of Round Rock", "Tyler CSS", "https://permits.roundrocktexas.gov/portal/"),
    ManualPortalAdapter("City of Pflugerville", "PublicAccess", "https://ams.pflugervilletx.gov/PublicAccess/default.aspx"),
    MgoAdapter("City of Cedar Park", "MyGovernmentOnline", "https://www.mygovernmentonline.org/"),
    MgoAdapter("City of Georgetown", "MyGovernmentOnline", "https://www.mygovernmentonline.org/"),
    TylerCssAdapter("City of Leander", "Tyler CSS", "https://permits.leandertx.gov/portal/"),
    ManualPortalAdapter("City of Hutto", "GovWell", "https://huttotx.portal.iworq.net/portalhome/huttotx"),
    CountyAdapter("Travis County (TNR)", "E-Permitting", "https://www.traviscountytx.gov/tnr/permits"),

    # Hays County & cities
    CountyAdapter("Hays County", "Inspections & Permitting", "https://hayscountytx.com/departments/development-services/inspections-and-permitting/"),
    MgoAdapter("City of Buda", "MyGovernmentOnline", "https://www.mygovernmentonline.org/"),
    TylerCssAdapter("City of Kyle", "Tyler CSS", "https://etrakit.cityofkyle.com/"),
    ManualPortalAdapter("City of San Marcos", "Permit Portal", "https://sanmarcostx.gov/1783/Permits-Inspections"),

    # Harris County / Houston
    ManualPortalAdapter("Harris County", "ePermits", "https://www.hcpid.org/epermits"),
    ManualPortalAdapter("City of Houston", "Houston Permit Portal", "https://www.houstonpermittingcenter.org/permits")
]

def adapters_for(county: Optional[str], city: Optional[str]) -> List[BaseAdapter]:
    \"\"\"
    Simple routing:
    - If city == Austin -> keep Austin first, then the rest.
    - If county == Harris -> bias Houston/Harris earlier.
    - Otherwise: keep defined order.
    \"\"\"
    order = ADAPTERS_IN_ORDER[:]
    if county and "Harris" in county:
        # Move Houston/Harris up after Austin
        houston = [a for a in order if getattr(a, "name", "").startswith("City of Houston")]
        harris = [a for a in order if getattr(a, "name", "").startswith("Harris County")]
        rest = [a for a in order if a not in houston + harris + [order[0]]]
        return [order[0]] + houston + harris + rest
    return order

# ---------- API endpoint ----------

@app.get("/search_permits", response_model=SearchResponse)
def search_permits(address: str = Query(..., description="Full street address, city, state, ZIP")):
    addr_in = norm(address)
    if not addr_in:
        raise HTTPException(status_code=400, detail="address is required")

    # 1) Resolve city/county
    geo = geocode_nominatim(addr_in)
    city = geo.get("city")
    county = geo.get("county")

    checked: List[str] = []
    all_hits: List[Permit] = []

    # 2) Try adapters in a smart order
    for adapter in adapters_for(county, city):
        checked.append(adapter.name)
        try:
            hits = adapter.search(addr_in, city, county)
            if hits:
                all_hits.extend(hits)
                # If we found any real permits (with id), stop early
                has_real = any(h.permit_id for h in hits)
                if has_real:
                    break
            time.sleep(0.4)
        except Exception:
            # swallow and continue
            continue

    return SearchResponse(
        address_input=addr_in,
        resolved_city=city,
        resolved_county=county,
        hits=all_hits,
        checked=checked
    )
