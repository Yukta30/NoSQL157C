// =====================================================================
// CS 157C Project - Neo4j schema (Neo4j 5.x syntax, works on AuraDB)
// Run once on an empty database BEFORE loading any CSVs.
// Contract: docs/csv_contract.md
// =====================================================================

// ---------- Uniqueness constraints (also create the lookup indexes) ----------
CREATE CONSTRAINT user_id IF NOT EXISTS
FOR (u:User) REQUIRE u.userId IS UNIQUE;

CREATE CONSTRAINT user_username IF NOT EXISTS
FOR (u:User) REQUIRE u.username IS UNIQUE;

CREATE CONSTRAINT skill_name IF NOT EXISTS
FOR (s:Skill) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT interest_name IF NOT EXISTS
FOR (i:Interest) REQUIRE i.name IS UNIQUE;

CREATE CONSTRAINT competition_id IF NOT EXISTS
FOR (c:Competition) REQUIRE c.competitionId IS UNIQUE;

CREATE CONSTRAINT team_id IF NOT EXISTS
FOR (t:Team) REQUIRE t.teamId IS UNIQUE;

// App projects (backend/projects.py)
CREATE CONSTRAINT project_id IF NOT EXISTS
FOR (p:Project) REQUIRE p.projectId IS UNIQUE;

// ---------- Search & filter indexes ----------
// Discover page: search by username / display name ("Alex")
CREATE FULLTEXT INDEX user_search IF NOT EXISTS
FOR (u:User) ON EACH [u.username, u.displayName];

// Compatibility filters / team builder
CREATE INDEX user_tier IF NOT EXISTS FOR (u:User) ON (u.tier);
CREATE INDEX user_comp_tier IF NOT EXISTS FOR (u:User) ON (u.compTier);
CREATE INDEX user_source IF NOT EXISTS FOR (u:User) ON (u.source);
// No country index: Users.Country is empty for ~96% of accounts.

// Skill pickers grouped by category (data type / task / technique / analysis / packages)
CREATE INDEX skill_category IF NOT EXISTS FOR (s:Skill) ON (s.category);

// Competition browsing
CREATE INDEX competition_year IF NOT EXISTS FOR (c:Competition) ON (c.year);
CREATE INDEX competition_segment IF NOT EXISTS FOR (c:Competition) ON (c.segment);

// =====================================================================
// Graph model (reference - not executable)
//
// (:User {userId, username, displayName, tier, country, registerDate,
//         compTier, golds, silvers, bronzes, source})
// tier/compTier values: novice | expert | master | grandmaster | staff
// (:Skill {name, category, tagId})        // data type / task / technique / analysis / packages tags
// (:Interest {name, category, tagId})     // subject tags (finance, health, sports, ...)
// (:Competition {competitionId, slug, title, segment, year, maxTeamSize, totalTeams})
// (:Team {teamId, teamName, medal, privateRank, rankPct, teamSize})
//
// (User)-[:MEMBER_OF]->(Team)
// (Team)-[:PARTICIPATED_IN]->(Competition)
// (Competition)-[:USES_SKILL]->(Skill)
// (Competition)-[:ABOUT]->(Interest)
// (User)-[:HAS_SKILL {weight, competitions, medals, source}]->(Skill)
// (User)-[:INTERESTED_IN {weight, competitions, source}]->(Interest)
// (User)-[:FOLLOWS {since}]->(User)
// (User)-[:WORKED_WITH {times}]-(User)   // derived after load, see contract section 6
//
// App projects (created in the app, never loaded from CSV; see backend/projects.py):
// (:Project {projectId, title, description, teamSize, status, createdAt})
// (User)-[:OWNS]->(Project)
// (User)-[:JOINED {role, since}]->(Project)
// (User)-[:INVITED {status, invitedBy, message, at, respondedAt}]->(Project)
// (Project)-[:NEEDS]->(Skill)
// =====================================================================
