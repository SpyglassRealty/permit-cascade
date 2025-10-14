from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(
    title="Permit Search Cascade",
    description="Fetches building permit data by address from the Permit Cascade API.",
    version="1.0.1"
)

# ✅ Enable CORS for ChatGPT MCP and any frontend use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this later to specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Data Models ----------

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
    raw: Optional[dict] = None


class SearchResponse(BaseModel):
    address_input: str
    resolved_city: str
    resolved_county: str
    hits: List[Permit]
    checked: List[str] = []


# ---------- Routes ----------

@app.get("/", response_model=str)
def root():
    return "Permit Search API is running."


@app.get("/search_permits", response_model=SearchResponse)
def search_permits(address: str = Query(..., description="Full street address, city, state, ZIP")):
    # Simulated example output — replace this logic with your actual permit lookup later
    return SearchResponse(
        address_input=address,
        resolved_city="Austin",
        resolved_county="Travis County",
        hits=[
            Permit(
                jurisdiction="City of Austin",
                portal="Austin Build + Connect",
                manual_check_url="https://abc.austintexas.gov/public-search"
            ),
            Permit(
                jurisdiction="City of Round Rock",
                portal="Tyler CSS",
                manual_check_url="https://www.roundrocktexas.gov"
            ),
        ],
        checked=["Austin", "Round Rock"]
    )

# ---------- Run locally ----------
# To run locally: uvicorn main:app --reload

