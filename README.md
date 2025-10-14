# Permit Cascade

A tiny FastAPI service that your OpenAI Agent can call to search building permits across multiple jurisdictions.
- Calls City of Austin first, then falls back to other cities/counties in Travis, Williamson, Hays, and Harris.
- Returns normalized JSON results or "manual_check_url" links for portals without public APIs.

## Deploy on Render (no terminal)
1. Create a new GitHub repo and upload these files.
2. In Render: New → Web Service → Public Git Repository → paste your repo URL → Connect.
3. Render will auto-detect `render.yaml` and deploy.
4. After it is Live, open: `https://<your-service>.onrender.com/docs`
5. In your Agent, import the OpenAPI schema from `https://<your-service>.onrender.com/openapi.json`

## Where to paste your Austin logic
Edit `main.py` → `AustinAdapter.search()`.
Return a list of `Permit(...)` entries or `[]` if none.
