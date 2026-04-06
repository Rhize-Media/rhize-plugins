// ============================================================
// Content Flywheel — Core Types
// ============================================================

// --- Pipeline ---

export type PipelineStage =
  | "inspiration"
  | "research"
  | "draft"
  | "optimize"
  | "review"
  | "published"
  | "monitor"
  | "refresh";

export const PIPELINE_STAGES: {
  name: PipelineStage;
  label: string;
  order: number;
  color: string;
}[] = [
  { name: "inspiration", label: "Inspiration", order: 0, color: "#a78bfa" },
  { name: "research", label: "Research", order: 1, color: "#60a5fa" },
  { name: "draft", label: "Draft", order: 2, color: "#fbbf24" },
  { name: "optimize", label: "Optimize", order: 3, color: "#f97316" },
  { name: "review", label: "Review", order: 4, color: "#fb7185" },
  { name: "published", label: "Published", order: 5, color: "#34d399" },
  { name: "monitor", label: "Monitor", order: 6, color: "#2dd4bf" },
  { name: "refresh", label: "Refresh", order: 7, color: "#c084fc" },
];

// --- Content ---

export interface ContentPiece {
  id: string;
  title: string;
  slug: string;
  stage: PipelineStage;
  author: string;
  url?: string;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
}

export interface Keyword {
  id: string;
  term: string;
  volume: number;
  difficulty: number;
  intent: "informational" | "navigational" | "commercial" | "transactional";
  cpc?: number;
  clusterId?: string;
}

export interface KeywordCluster {
  id: string;
  name: string;
  pillarTopic: string;
}

export interface SERPSnapshot {
  id: string;
  contentId: string;
  keywordId: string;
  position: number;
  date: string;
  features: string[];
  aiOverviewCited: boolean;
}

export interface BacklinkSource {
  id: string;
  domain: string;
  authorityRank: number;
  anchorText: string;
}

export interface Author {
  id: string;
  name: string;
  bio?: string;
  expertise: string[];
}

// --- CMS / Distribution (agnostic) ---

export type CMSType = "sanity" | "wordpress" | "custom";
export type DistributionType = "ghl" | "buffer" | "native";

export interface CMSTarget {
  id: string;
  type: CMSType;
  projectId?: string;
  dataset?: string;
}

export interface DistributionChannel {
  id: string;
  type: DistributionType;
  platform: string;
  accountId?: string;
}

// --- Adapter interfaces ---

export interface CMSDocument {
  id: string;
  url?: string;
  status: "draft" | "published" | "scheduled";
}

export interface CMSAdapter {
  createDraft(content: ContentPiece): Promise<CMSDocument>;
  updateDraft(
    id: string,
    content: Partial<ContentPiece>
  ): Promise<CMSDocument>;
  publish(id: string): Promise<{ url: string }>;
  unpublish(id: string): Promise<void>;
  getStatus(id: string): Promise<"draft" | "published" | "scheduled">;
}

export interface SocialPost {
  contentId: string;
  platform: string;
  text: string;
  mediaUrls?: string[];
}

export interface PostResult {
  id: string;
  platform: string;
  status: "scheduled" | "posted" | "failed";
  scheduledAt?: string;
}

export interface DistributionAdapter {
  schedulePost(content: SocialPost, scheduledAt: Date): Promise<PostResult>;
  getPostStatus(
    id: string
  ): Promise<"scheduled" | "posted" | "failed">;
  listPlatforms(): Promise<string[]>;
}

// --- Workflow output types ---

export interface SEOScore {
  id: string;
  contentId: string;
  overall: number;
  titleScore: number;
  metaScore: number;
  headingScore: number;
  eeatScore: number;
  internalLinkScore: number;
  structuredDataScore: number;
  wordCount: number;
  recommendations: string[];
  date: string;
}

export interface AIVisibilitySnapshot {
  id: string;
  contentId: string;
  llm: string;
  mentionRate: number;
  accuracy: number;
  citationCount: number;
  date: string;
}

export interface Competitor {
  id: string;
  domain: string;
  authorityRank: number;
}

export interface StageTransition {
  from: PipelineStage;
  to: PipelineStage;
  enteredAt: string;
  leftAt: string;
}

export interface SiteAudit {
  id: string;
  domain: string;
  totalPages: number;
  criticalIssues: number;
  highIssues: number;
  mediumIssues: number;
  lowIssues: number;
  date: string;
}

export type WorkflowType =
  | "keyword-research"
  | "content-optimize"
  | "serp-analysis"
  | "backlink-analysis"
  | "ai-visibility"
  | "site-audit";

export interface WorkflowRun {
  id: string;
  type: WorkflowType;
  contentId?: string;
  status: "running" | "completed" | "failed";
  startedAt: string;
  completedAt?: string;
  error?: string;
  summary?: string;
}
