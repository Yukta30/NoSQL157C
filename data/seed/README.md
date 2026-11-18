# Seed graph

A small, hand-designed graph for developing and testing before the real data is ready. It follows `docs/csv_contract.md` exactly, so the loader works on it unchanged.

- **Regenerate:** `python scripts/make_seed.py` (deterministic). Edit the scenario tables in that script, not the CSVs.
- **Everything is fictional:** people, IDs and competitions. Tag names and categories are real Kaggle ones; tag IDs are not.
- **Never load seed and real data into the same database.** IDs like `k1001` could collide with real Kaggle users.
- **Weights follow contract section 4:** user→tag pairs come from graph teams; weights come from full history. The script includes "hidden" history competitions that are not in the CSVs, the same way real history teams aren't exported.

## Expected counts after loading

| Nodes | | Relationships | |
|---|---|---|---|
| User | 27 (25 Kaggle + 2 app) | MEMBER_OF | 36 |
| Skill | 9 | PARTICIPATED_IN | 16 |
| Interest | 5 | USES_SKILL | 15 |
| Competition | 7 | ABOUT | 8 |
| Team | 16 | HAS_SKILL | 74 |
| | | INTERESTED_IN | 42 |
| | | FOLLOWS | 18 |
| | | WORKED_WITH (derived) | 22 |
| **Total** | **64** | **Total** | **231** |

WORKED_WITH pairs with `times = 2`: `alicechen–bobsmith`, `davepatel–frankmuller`. All other pairs have `times = 1`.

## The cast

| User | Story | What it tests |
|---|---|---|
| `alicechen`, `bobsmith`, `carolwu` | NLP team (gold, C3). Alice and Bob also teamed in C7 and follow each other. Carol follows both. | Strong social and skill cluster. WORKED_WITH `times = 2`. Display name with a comma (`Carol Wu, PhD`). |
| `davepatel`, `frankmuller`, `gracekim` | Tabular / forecasting crew (C1, C4). | Grace's only team is in C4, which has no interest tag, so she has **no INTERESTED_IN**. Frank's display name has quotes and an umlaut. |
| `erinokafor`, `heidilarsen`, `ivanpetrov`, `judygarcia` | Vision people (C2, C6). Erin and Heidi follow each other. Judy follows Heidi and worked with her. | Mutual-connection path `judy → heidi → erin`. |
| `mallorystone`, `niajsingh`, `oliviabrown` | Mallory's only team is in C5 (sports, no skill tag). | Mallory has **no HAS_SKILL**, even though her hidden history includes an NLP competition: history alone never creates a pair. |
| `peggyhopper` | Grandmaster with teams in C3, C6, C4, followed by five users. | Highest weights (0.93–0.95); she covers NLP, CV and time series alone. Most-followed user. |
| `trentnguyen`, `sybilrao`, `victorli`, `wendyclark` | Peggy's / Wendy's teammates. | Emoji (`Sybil Rao 🚀`, team `🔬 Microscope Gang`) and CJK (`李伟 (Victor Li)`) in names. |
| `walterkaggle` | Staff tier, no Competitions achievement row. | `compTier` empty and medal totals 0 despite a bronze team (contract: default 0). |
| `zaraahmed`, `quentinmoreau`, `rupertgray` | Same tags as Judy (C2), with no social ties to anyone outside their team. | Skill overlap without social proximity. 3-person team. Apostrophe in a name. |
| `umasato`, `xavierdiaz`, `yolandaruiz` | Filler with modest weights. | — |
| `newbie_sam` (app) | Self-declared `nlp`, `text`, interest `health`. Follows Alice. No teams. | `source = 'self'` relationships with weight 0.5; app user with no history. |
| `lee_app` (app) | Just registered: no skills, interests, follows or teams. | Every "empty" code path. |

## Expected answers

These describe what any reasonable implementation must do. They're phrased to be robust to tuning, so they don't pin exact scores. Turn each into a pytest against a database loaded with this seed.

### Search and profile
- `search_users("chen")` → only `alicechen`.
- `search_users("carol")` → `carolwu`, with the display name `Carol Wu, PhD` intact.
- `search_users("")` and `search_users("zzzz")` → `[]`, no exception.
- `get_profile(mallorystone)` → `skills == []`, `interests == ["sports"]`.
- `get_profile(walterkaggle)` → `compTier` is null and medals are all 0.
- `get_profile(lee_app)` → empty skills, interests, followers, following and teams, no exception.
- Unknown user ID → a clear "not found" result, not a crash.

### Follow / unfollow
- `follow(newbie_sam, bobsmith)` creates exactly one FOLLOWS. Calling it again still leaves one (MERGE).
- `unfollow` on a follow that doesn't exist → no error.
- `follow(x, x)` → rejected.

### Recommendations
- A user's own ID is never returned.
- `recommend(lee_app)` → `[]`, no exception.
- `recommend(judygarcia)`: among users Judy has no direct relationship with (i.e. excluding `heidilarsen` and `peggyhopper`), **`erinokafor` ranks first**. Zara, Quentin, Rupert and Bob share the same C2 tags, but Erin has the higher weights, the matching interests, and the mutual connection through Heidi. Erin's reasons should mention Heidi or shared computer vision.
- `recommend(mallorystone)` is **not empty** even though she has no skills, because social signals carry it. It includes `oliviabrown` (her teammate's teammate, via Niaj).
- `recommend(newbie_sam)`: the top 3 all have `nlp` or `text`. `bobsmith` and `carolwu` rank high (shared skills, and two hops away through Alice).
- `recommend(davepatel)`: no vision-only user (`zaraahmed`, `quentinmoreau`, `rupertgray`, `ivanpetrov`, `judygarcia`) in the top 5.

### Build My Team
- `build_team(["nlp", "computer vision", "time series analysis"], size=3)` → full coverage (no `None`). Both `peggyhopper` and `bobsmith` cover all three alone. With weighted coverage Peggy is the first pick (0.93 / 0.63 / 0.86 vs Bob's 0.81 / 0.34 / 0.49).
- `build_team(["nlp", "computer vision"], size=2, seed_user_id=alicechen)` → Alice plus one member with `computer vision`. If a social bonus is applied, that member is `bobsmith` (worked together twice, mutual follow).
- `build_team(["tensorflow", "binary classification"], size=1)` → **exactly one `None` in coverage**. Nobody has both:
  - tensorflow: Erin, Heidi, Ivan, Peggy, Sybil
  - binary classification: Dave, Frank, Niaj, Olivia, Uma, Xavier
- The same request with `size=2` → full coverage, one person from each group.
- Invalid input is rejected with a message, not a crash:
  - an unknown skill (`"basket weaving"`)
  - an interest passed as a skill (`"finance"`)
  - `size < 1`
  - an empty skill list

### Network view
- `get_neighborhood(peggyhopper, hops=1)` includes at least 5 incoming FOLLOWS edges (Grace, Sybil, Trent, Niaj, Judy) and WORKED_WITH edges to Trent, Sybil and Victor.
- `limit` is respected: the result never has more nodes than `limit`.
- Names with emoji, quotes and CJK render correctly as node labels.
