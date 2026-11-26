# TeaMatcha: CS 157C Neo4j Teammate Matcher

A Neo4j-powered social network for skill-based discovery and teammate recommendations, seeded from [Meta Kaggle](https://www.kaggle.com/datasets/kaggle/meta-kaggle).

## Layout

```
database/schema.cypher      constraints + indexes (run first on an empty DB)
docs/csv_contract.md        preprocessing -> loader contract (columns, IDs, rules)
data/seed/                  small hand-designed graph + expected answers for tests
data/raw/                   Meta Kaggle CSVs (gitignored; download per contract §1)
data/processed/             preprocess_data.py output (gitignored)
scripts/make_seed.py        regenerates data/seed/
scripts/verify_sources.py   week-1 checks of the raw files
frontend/app.py             Streamlit app (pages in frontend/app_pages/)
```

Planned (see the architecture doc): `scripts/preprocess_data.py`, `scripts/load_neo4j.py`, `backend/`, `frontend/`.

## Running the frontend

Develop against a local Neo4j loaded with the seed graph. Don't use the shared instance: following people from the UI writes to the database, and `tests/test_backend.py` expects the seed data exactly.

1. Start Neo4j 5 locally, e.g. with Docker (pick your own password):
   ```
   docker run -d --name teamatcha-neo4j -p 7474:7474 -p 7687:7687 -v teamatcha-neo4j-data:/data -e NEO4J_AUTH=neo4j/<password> neo4j:5
   ```
   Later sessions: `docker start teamatcha-neo4j`.
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` in the project root (gitignored, never commit it):
   ```
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=<password>
   NEO4J_DATABASE=neo4j
   ```
4. Load the seed graph (applies the schema too). The loader reads the variables from the shell, not `.env`, so export them first (bash: `set -a; . ./.env; set +a`):
   ```
   python scripts/load_neo4j.py --data-dir data/seed --wipe
   ```
   Run it again any time to reset the data.
5. Run the app from the project root: `streamlit run frontend/app.py`

There are no accounts: pick whose view to show in the sidebar. `k1001` (Alice) has lots of data; Lee (`u5eed0000000000000000000000000002`) has none, for checking empty states.

## Changing shared files

`database/schema.cypher`, `docs/csv_contract.md` and the backend API signatures are shared contracts. Get a quick OK from the team before changing them.
