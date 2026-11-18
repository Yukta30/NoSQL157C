# CSV Contract — Meta Kaggle → Neo4j

This file is the agreement between **preprocessing** (`scripts/preprocess_data.py`, P1) and **loading** (`scripts/load_neo4j.py`, P2). Recommendations (P3) and the UI (P4) depend on the property names defined here.
**Any change needs a quick OK from the whole team.**

Graph schema: `database/schema.cypher`. Source: [Meta Kaggle](https://www.kaggle.com/datasets/kaggle/meta-kaggle). Column names and the counts below were checked against the files dated 2026-11-16 (`scripts/verify_sources.py` plus follow-up queries).

---

## 1. Source files

Download **only** these files. Unzip any that arrive zipped. Put them in `data/raw/`, which is gitignored.

```bash
for f in Users Teams TeamMemberships Competitions CompetitionTags Tags UserAchievements UserFollowers; do
  kaggle datasets download kaggle/meta-kaggle -f "$f.csv" -p data/raw
done
```

| File | Size | Columns we use | Notes |
|---|---|---|---|
| `Competitions.csv` | 187 MB | `Id, Slug, Title, HostSegmentTitle, EnabledDate, DeadlineDate, MaxTeamSize, TotalTeams` | Has multi-line text columns (`Overview`, `Rules`), so use a real CSV parser and read only these columns. 12,878 rows. |
| `CompetitionTags.csv` | 31 KB | `CompetitionId, TagId` | 1,315 rows, **539 competitions**, 157 distinct tags. |
| `Tags.csv` | 0.1 MB | `Id, Name, FullPath` | `FullPath` is a category path, e.g. `task > regression`, `subject > health and fitness > exercise > sports`. All tag names used by competitions are already lowercase. |
| `Teams.csv` | 799 MB | `Id, CompetitionId, TeamName, IsBenchmark, Medal, PrivateLeaderboardRank` | `Medal`: `1` gold, `2` silver, `3` bronze; `0` or empty = none. |
| `TeamMemberships.csv` | 443 MB | `TeamId, UserId` | Contains members whose accounts no longer exist in `Users.csv`. |
| `Users.csv` | 2.7 GB | `Id, UserName, DisplayName, RegisterDate, PerformanceTier, Country` | 34.86M rows. **Filter to subset users early.** `Country` is empty for ~96% of users. |
| `UserAchievements.csv` | 10.4 GB | `UserId, AchievementType, Tier, TotalGold, TotalSilver, TotalBronze` | 4 rows per user (Competitions/Scripts/Discussion/Datasets). Keep `AchievementType = 'Competitions'` only. Some users have no row. |
| `UserFollowers.csv` | 86 MB | `UserId, FollowingUserId, CreationDate` | `UserId` follows `FollowingUserId` (section 8). 1.96M rows, no self-follows or duplicate pairs. |

**Skip:** `Submissions` (2.7 GB), `KernelVersions` (5.1 GB), `ForumMessages` (1.8 GB), `Episodes`/`EpisodeAgents` (39 GB), `DatasetVersions` (1.6 GB).

**Source formats:**

| Column(s) | Format |
|---|---|
| `Competitions.EnabledDate`, `Competitions.DeadlineDate` | `%m/%d/%Y %H:%M:%S` (e.g. `05/25/2010 18:00:00`) |
| `Users.RegisterDate`, `UserFollowers.CreationDate` | `%m/%d/%Y` |

- Booleans are the strings `"True"`/`"False"`.
- Every value is quoted.
- Empty string means null.

Use DuckDB (or Polars lazy) for anything over a few hundred MB. Pandas is fine for the small files.

---

## 2. Subset rule

**Why a medal rule:** the tagged competitions alone hold 7.25M teams. 7.12M of them are solo and 6.44M were never ranked. No `MIN_YEAR`/`MIN_COMPS` setting brings that under AuraDB Free's cap of **200k nodes / 400k relationships** (checked 2026-11-17). The graph therefore keeps **ranked, medal-winning teams with at least two members**: the best evidence of real collaboration, across all years.

1. **Competitions (candidates):** ≥ 1 row in `CompetitionTags` **and** `HostSegmentTitle` in (`Featured`, `Research`, `Playground`, `Recruitment`). That gives 529 competitions.
2. **Teams:** in those competitions, with all of:
   - `IsBenchmark = 'False'`
   - `PrivateLeaderboardRank` is not null
   - `Medal` in (`1`, `2`, `3`)
   - ≥ 2 **existing members**: members present in `Users.csv`, excluding `Id = 1` (the Kaggle Team bot)
3. **Users:** the existing members of those teams.
4. **Competitions (final):** candidates with ≥ 1 kept team.

**Expected size** (exact counts under this rule, 2026-11-16 files, before the `packages` move in section 3):

| Users | Teams | Competitions | Skills | Interests | Nodes | Relationships | WORKED_WITH | FOLLOWS |
|---|---|---|---|---|---|---|---|---|
| 29,761 | 15,391 | 317 | 46 | 71 | 45,586 | 317,699 | 56,183 | 92,385 |

- Moving `packages` to Skill adds 2 skill nodes, 2 `USES_SKILL` and a small number of `HAS_SKILL`.
- That leaves roughly 80k relationships for app users and demo activity.
- Competition years in the final subset run from 2015 to 2026.

**If it grows too big** after future dataset updates, add `MIN_YEAR` on `DeadlineDate` as an extra filter. Print the node/relationship counts at the end of every run.

**Note:** the cap only applies to AuraDB Free. On a local Neo4j Desktop instance there's no limit, so a looser rule would work. Either way, keep this rule for the shared instance.

---

## 3. Output files (`data/processed/`)

### Global formatting rules
- UTF-8, header row, comma-separated, standard quoting. Team and display names contain commas, quotes and emoji.
- Empty string = null. Never write `NaN`, `None` or `null`.
- Output dates are ISO `YYYY-MM-DD`.
- Integers have no decimals. Write `3`, not `3.0`; watch for pandas turning int columns with nulls into floats.
- **Every ID in a relationship file must exist in its node file.** Filter relationships **after** the node subset is final.

### ID formats
| Entity | Format | Example |
|---|---|---|
| Kaggle user | `k` + Kaggle `Users.Id` | `k368` |
| App-registered user | `u` + UUID4 hex | `u3f2a9c...` |
| Competition | Kaggle `Competitions.Id` (int) | `2435` |
| Team | Kaggle `Teams.Id` (int) | `505` |
| Skill / Interest | tag `Name` (lowercase, as in `Tags.csv`) | `computer vision` |

### Tier mapping
Used for both `tier` and `compTier`:

| Code | Label |
|---|---|
| `0`, `1` | `novice` |
| `2` | `expert` |
| `3` | `master` |
| `4` | `grandmaster` |
| `5` | `staff` |

- `Users.PerformanceTier` never uses `0`; `1` is the base tier for 99.9% of accounts. The data can't distinguish novice from contributor, so both codes map to `novice`.
- `UserAchievements.Tier` uses `0`–`4`.
- `tier` is the best tier across all Kaggle categories. **Use `compTier` for competition strength:** 692 users are overall grandmasters, but only 410 are Competitions grandmasters.

### Node files

**`users.csv`**
| Column | Type | Source / rule |
|---|---|---|
| `userId` | string | `"k" + Users.Id` |
| `username` | string | `Users.UserName` (unique; verified in the subset) |
| `displayName` | string | `Users.DisplayName` |
| `tier` | string | `Users.PerformanceTier`, mapped with the tier table |
| `country` | string? | `Users.Country`. Mostly empty, so don't use it in scoring. |
| `registerDate` | date | `Users.RegisterDate` → ISO |
| `compTier` | string? | `UserAchievements.Tier` (Competitions row), mapped with the tier table. Empty if the user has no row. |
| `golds` / `silvers` / `bronzes` | int | `TotalGold/TotalSilver/TotalBronze` (Competitions row), default `0` |
| `source` | string | `kaggle` for real data; the app writes `app`. The seed data (`data/seed/`) contains both, so the loader must not assume `kaggle`. |

**`skills.csv`** and **`interests.csv`**
| Column | Type | Rule |
|---|---|---|
| `name` | string | `Tags.Name`, lowercase |
| `category` | string | 1st segment of `Tags.FullPath` |
| `tagId` | int | `Tags.Id` |

The `FullPath` category decides which file a tag goes into:
- **Skill:** `data type`, `task`, `technique`, `analysis`, `packages` (e.g. tabular, image, text, regression, computer vision, nlp, time series analysis, optimization, numpy, tensorflow). In the 529 candidate competitions there are 58 skill tags (56 + the 2 `packages` tags).
- **Interest:** `subject` (e.g. biology, finance, health, sports, medicine). There are 86.
- **Dropped:** everything else (12 tags): `audience`, `geography and places`, `admin`, `architecture`, `language` (`bengali`, `english`, which are spoken languages).

Only include tags used by at least one competition in the final subset. These files are also the fixed vocabulary for the skill/interest pickers in the app.

**`competitions.csv`**
| Column | Type | Rule |
|---|---|---|
| `competitionId` | int | `Competitions.Id` |
| `slug` | string | `Slug` |
| `title` | string | `Title` |
| `segment` | string | `HostSegmentTitle` |
| `year` | int | year of `DeadlineDate` (parsed with `%m/%d/%Y %H:%M:%S`) |
| `maxTeamSize` | int? | `MaxTeamSize` |
| `totalTeams` | int? | `TotalTeams` as Kaggle reports it (can be `0`, so don't divide by it) |

**`teams.csv`**
| Column | Type | Rule |
|---|---|---|
| `teamId` | int | `Teams.Id` |
| `competitionId` | int | `Teams.CompetitionId` (loader creates `PARTICIPATED_IN` from this) |
| `teamName` | string | `TeamName` |
| `medal` | string | `1`→`gold`, `2`→`silver`, `3`→`bronze` (always set under the subset rule) |
| `privateRank` | int | `PrivateLeaderboardRank` |
| `rankPct` | float | `privateRank / fieldSize`, rounded to 4 dp, where `fieldSize` = max `PrivateLeaderboardRank` over **all** ranked teams in that competition in `Teams.csv`. 0 = top; lower is better. |
| `teamSize` | int | number of existing members (same rule as section 2), which equals the team's `MEMBER_OF` count in the graph |

### Relationship files

| File | Columns | Creates |
|---|---|---|
| `member_of.csv` | `userId, teamId` | `(User)-[:MEMBER_OF]->(Team)` |
| `competition_skill.csv` | `competitionId, skill` | `(Competition)-[:USES_SKILL]->(Skill)` |
| `competition_interest.csv` | `competitionId, interest` | `(Competition)-[:ABOUT]->(Interest)` |
| `user_skill.csv` | `userId, skill, weight, competitions, medals, source` | `(User)-[:HAS_SKILL]->(Skill)` |
| `user_interest.csv` | `userId, interest, weight, competitions, source` | `(User)-[:INTERESTED_IN]->(Interest)` |
| `follows.csv` | `followerId, followeeId, since` | `(User)-[:FOLLOWS {since}]->(User)`. `followerId = "k" + UserId`, `followeeId = "k" + FollowingUserId`, `since = CreationDate` → ISO. Keep only rows where both users are in the subset. |

---

## 4. Derivation rules

Two sets of teams are involved:

- **Graph teams:** the medal teams from section 2. They decide **which** user→tag pairs exist.
- **History teams:** every ranked, non-benchmark team a kept user was on in the 529 candidate competitions, **including solo and non-medal results**. These decide the **weights**.

That way the relationship count matches the size estimate, while each weight still reflects the user's full record. History teams are used only for these calculations and are not exported as nodes.

### HAS_SKILL (what you've shown you can do)
- A pair (U, S) **exists** if U was on a graph team in a competition tagged with skill S.
- For each existing pair, score every history team U was on in a competition tagged with S:

| Team result | Points |
|---|---|
| gold | 3 |
| silver | 2 |
| bronze | 1 |
| no medal, `rankPct` ≤ 0.25 | 0.75 |
| no medal, otherwise | 0.25 |

Add up the points for those teams to get `points`. Then:

- `weight = round(1 - exp(-points / 3), 4)`. This is between 0 and 1 and levels off: one bronze ≈ 0.28, one gold ≈ 0.63, two golds ≈ 0.86.
- `competitions` = number of those history teams; `medals` = how many of them medaled (used for explanations like "2 medals in NLP").
- `source` = `kaggle`.

**Notes:**
- 41 of the 317 final competitions have no skill tag. Their teams create no HAS_SKILL, but they still count for WORKED_WITH and INTERESTED_IN. As a result, 2,476 kept users have no HAS_SKILL and 6,165 have no INTERESTED_IN. The app must handle both (empty sections on the profile, and recommendations that rely on other signals).
- **Top users saturate.** With full-history points, prolific users hit `weight` 1.0 or close to it (e.g. `cdeotte`: 1.0 on `tabular` and `image`, > 0.9 on six more skills). So weight alone can't rank top users against each other; use `competitions` and `medals` to break ties.

### INTERESTED_IN (domains you choose to work in)
- A pair (U, I) **exists** if U was on a graph team in a competition tagged with subject I.
- Let `n` = the number of history teams U was on in competitions tagged with I.
- `weight = round(1 - exp(-n / 2), 4)`
- `competitions = n`, `source = kaggle`

### Not baked into the CSVs
Tag rarity (IDF), social proximity and compatibility are computed **at query time** by `recommendations.py`, so they can be tuned without re-running preprocessing.

### App-registered users
Users who sign up in the app pick skills and interests from the vocabulary. The app writes the same relationships with `weight = 0.5`, `competitions = 0`, `source = 'self'`.

---

## 5. Load order (`load_neo4j.py`)

1. Run `database/schema.cypher`.
2. Nodes: `skills` → `interests` → `competitions` → `teams` (+ `PARTICIPATED_IN`) → `users`.
3. Relationships: `member_of` → `competition_skill` → `competition_interest` → `user_skill` → `user_interest` → `follows`.
4. Derived relationships (section 6).
5. Validation (section 7).

Use `MERGE` on the constrained key and batch large files in transactions of 10k rows (`CALL { … } IN TRANSACTIONS OF 10000 ROWS` with `LOAD CSV`, or `UNWIND $rows` from Python). Convert types explicitly: `toInteger()`, `toFloat()`, `date()`. Turn empty strings into null with `nullIf(x, '')`.

## 6. Derived: WORKED_WITH

```cypher
MATCH (a:User)-[:MEMBER_OF]->(t:Team)<-[:MEMBER_OF]-(b:User)
WHERE a.userId < b.userId
WITH a, b, count(t) AS times
CALL (a, b, times) {
  MERGE (a)-[w:WORKED_WITH]-(b)
  SET w.times = times
} IN TRANSACTIONS OF 10000 ROWS;
```
Run it from a Python session with an implicit transaction, or with `:auto` in Browser. Treat WORKED_WITH as undirected; always query it without an arrow: `(a)-[:WORKED_WITH]-(b)`. On older Neo4j 5 versions, write the subquery as `CALL { WITH a, b, times ... }`.

## 7. Validation (print after every load)

- The node count per label equals the row count of each node file.
- The relationship count per type equals the row count of each relationship file. Exception: `PARTICIPATED_IN`, which should equal the number of teams.
- Totals are close to section 2's counts (45,586 nodes and 317,699 relationships, plus the small `packages` additions) and under 200k / 400k.
- Zero orphans: `MATCH (t:Team) WHERE NOT (t)-[:PARTICIPATED_IN]->() RETURN count(t)` → 0.
- Every user with `source = 'kaggle'` has ≥ 1 `MEMBER_OF`, and every team has ≥ 2. App users have no teams.
- Spot check: `MATCH (u:User {username:'cdeotte'})-[r:HAS_SKILL]->(s) RETURN s.name, r.weight, r.competitions, r.medals ORDER BY r.weight DESC`. Expect several weights at or near 1.0 (section 4 explains why).

## 8. Verification log

- [x] **Follow direction:** `UserId` follows `FollowingUserId`. Sorted by `Id`, the file has runs of consecutive rows with the same `UserId` and different `FollowingUserId` values: one user following many accounts in a burst.
- [x] **`HostSegmentTitle`:** 7 values. The 4 segments in section 2 match exactly and cover 529 of the 539 tagged competitions; the 10 dropped are Community, Getting Started and Analytics.
- [x] **Dates:** Competitions use `%m/%d/%Y %H:%M:%S` (all 12,878 rows parse). Users and UserFollowers use `%m/%d/%Y`.
- [x] **Tiers:** 4 = grandmaster confirmed (11 known grandmasters checked); 5 = staff confirmed. `0`/`1` both map to `novice` (see the tier table).
- [x] **Subset size:** `MIN_YEAR`/`MIN_COMPS` alone can't fit (2025 + team ≥ 2 is still 678k relationships). Replaced by the medal-team rule in section 2. Exact counts were re-run under the "≥ 2 existing members" rule (238 medal teams drop out because of deleted members).
- [x] **`packages` and `language` tags:** `packages` = `numpy`, `tensorflow` (one competition each), moved to Skill. `language` = `bengali`, `english` (spoken languages), kept dropped.
- [x] **`rankPct` denominator:** `fieldSize` equals `TotalTeams` in all 515 competitions that have ranked teams, and no final competition has `TotalTeams = 0`.
- [ ] **Final pipeline counts:** once `preprocess_data.py` exists, confirm its output matches section 2, plus the `packages` additions.
