// ============================================================
// Content Flywheel — Neo4j Graph Schema
// Run this against your Neo4j instance to initialize the schema.
// Requires APOC plugin for some operations.
// ============================================================

// --- Constraints (uniqueness + existence) ---

CREATE CONSTRAINT content_id IF NOT EXISTS
FOR (c:ContentPiece) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT keyword_id IF NOT EXISTS
FOR (k:Keyword) REQUIRE k.id IS UNIQUE;

CREATE CONSTRAINT keyword_term IF NOT EXISTS
FOR (k:Keyword) REQUIRE k.term IS UNIQUE;

CREATE CONSTRAINT cluster_id IF NOT EXISTS
FOR (cl:KeywordCluster) REQUIRE cl.id IS UNIQUE;

CREATE CONSTRAINT stage_name IF NOT EXISTS
FOR (s:PipelineStage) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT author_id IF NOT EXISTS
FOR (a:Author) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT cms_target_id IF NOT EXISTS
FOR (t:CMSTarget) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT dist_channel_id IF NOT EXISTS
FOR (d:DistributionChannel) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT serp_snapshot_id IF NOT EXISTS
FOR (ss:SERPSnapshot) REQUIRE ss.id IS UNIQUE;

CREATE CONSTRAINT backlink_id IF NOT EXISTS
FOR (b:BacklinkSource) REQUIRE b.id IS UNIQUE;

// --- Workflow output node constraints ---

CREATE CONSTRAINT seo_score_id IF NOT EXISTS
FOR (s:SEOScore) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT ai_vis_id IF NOT EXISTS
FOR (a:AIVisibilitySnapshot) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT competitor_id IF NOT EXISTS
FOR (c:Competitor) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT competitor_domain IF NOT EXISTS
FOR (c:Competitor) REQUIRE c.domain IS UNIQUE;

CREATE CONSTRAINT workflow_run_id IF NOT EXISTS
FOR (w:WorkflowRun) REQUIRE w.id IS UNIQUE;

CREATE CONSTRAINT site_audit_id IF NOT EXISTS
FOR (a:SiteAudit) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT ai_usage_id IF NOT EXISTS
FOR (a:AIUsage) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT theme_name IF NOT EXISTS
FOR (t:Theme) REQUIRE t.name IS UNIQUE;

CREATE CONSTRAINT outline_id IF NOT EXISTS
FOR (o:Outline) REQUIRE o.id IS UNIQUE;

// --- Indexes for common lookups ---

CREATE INDEX content_slug IF NOT EXISTS
FOR (c:ContentPiece) ON (c.slug);

CREATE INDEX content_stage IF NOT EXISTS
FOR (c:ContentPiece) ON (c.stage);

CREATE INDEX keyword_volume IF NOT EXISTS
FOR (k:Keyword) ON (k.volume);

CREATE INDEX keyword_difficulty IF NOT EXISTS
FOR (k:Keyword) ON (k.difficulty);

CREATE INDEX serp_date IF NOT EXISTS
FOR (ss:SERPSnapshot) ON (ss.date);

CREATE INDEX seo_score_date IF NOT EXISTS
FOR (s:SEOScore) ON (s.date);

CREATE INDEX workflow_run_type IF NOT EXISTS
FOR (w:WorkflowRun) ON (w.type);

CREATE INDEX ai_vis_date IF NOT EXISTS
FOR (a:AIVisibilitySnapshot) ON (a.date);

CREATE INDEX ai_vis_content IF NOT EXISTS
FOR (a:AIVisibilitySnapshot) ON (a.contentId);

CREATE INDEX workflow_run_content IF NOT EXISTS
FOR (w:WorkflowRun) ON (w.contentId);

CREATE INDEX site_audit_domain IF NOT EXISTS
FOR (a:SiteAudit) ON (a.domain);

// --- Seed pipeline stages ---

MERGE (s:PipelineStage {name: "inspiration"})
SET s.label = "Inspiration", s.order = 0, s.color = "#a78bfa";

MERGE (s:PipelineStage {name: "research"})
SET s.label = "Research", s.order = 1, s.color = "#60a5fa";

MERGE (s:PipelineStage {name: "draft"})
SET s.label = "Draft", s.order = 2, s.color = "#fbbf24";

MERGE (s:PipelineStage {name: "optimize"})
SET s.label = "Optimize", s.order = 3, s.color = "#f97316";

MERGE (s:PipelineStage {name: "review"})
SET s.label = "Review", s.order = 4, s.color = "#fb7185";

MERGE (s:PipelineStage {name: "published"})
SET s.label = "Published", s.order = 5, s.color = "#34d399";

MERGE (s:PipelineStage {name: "monitor"})
SET s.label = "Monitor", s.order = 6, s.color = "#2dd4bf";

MERGE (s:PipelineStage {name: "refresh"})
SET s.label = "Refresh", s.order = 7, s.color = "#c084fc";
