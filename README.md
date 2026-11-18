# CS 157C — Neo4j Teammate Matcher

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
```

Planned (see the architecture doc): `scripts/preprocess_data.py`, `scripts/load_neo4j.py`, `backend/`, `frontend/`.

## Changing shared files

`database/schema.cypher`, `docs/csv_contract.md` and the backend API signatures are shared contracts. Get a quick OK from the team before changing them.
