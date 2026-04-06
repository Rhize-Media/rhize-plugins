import Anthropic from "@anthropic-ai/sdk";
import type { MessageParam } from "@anthropic-ai/sdk/resources/messages";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import type { z } from "zod";
import { getDriver } from "@/lib/neo4j/driver";
import type { AIModel } from "@/types";

// ---------------------------------------------------------------------------
// Model configuration
// ---------------------------------------------------------------------------

const MODEL_MAP: Record<AIModel, string> = {
  haiku: "claude-haiku-4-5-20251001",
  sonnet: "claude-sonnet-4-5-20250929",
};

// Per-million-token pricing (USD) — update when Anthropic changes pricing
const PRICING: Record<string, { input: number; output: number; cacheWrite: number; cacheRead: number }> = {
  [MODEL_MAP.haiku]:  { input: 0.80, output: 4.00, cacheWrite: 1.00, cacheRead: 0.08 },
  [MODEL_MAP.sonnet]: { input: 3.00, output: 15.00, cacheWrite: 3.75, cacheRead: 0.30 },
};

// ---------------------------------------------------------------------------
// Client singleton
// ---------------------------------------------------------------------------

let client: Anthropic | null = null;

function getClient(): Anthropic {
  if (client) return client;
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error(
      "Missing ANTHROPIC_API_KEY. Set it in .env.local or Vercel environment variables."
    );
  }
  client = new Anthropic({ apiKey, maxRetries: 3 });
  return client;
}

// Exported for testing — allows injecting a mock client
export function _setClient(mock: Anthropic | null): void {
  client = mock;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CacheableSystemMessage {
  type: "text";
  text: string;
  cache_control?: { type: "ephemeral" };
}

export interface GenerateTextParams {
  model?: AIModel;
  system: string | CacheableSystemMessage[];
  messages: MessageParam[];
  maxTokens?: number;
  temperature?: number;
  contentId?: string;
}

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cacheCreationInputTokens: number;
  cacheReadInputTokens: number;
  cost: number;
}

export interface GenerateTextResult {
  text: string;
  usage: TokenUsage;
}

export interface GenerateStructuredParams<T extends z.ZodType> {
  model?: AIModel;
  system: string | CacheableSystemMessage[];
  messages: MessageParam[];
  schema: T;
  maxTokens?: number;
  temperature?: number;
  contentId?: string;
}

// ---------------------------------------------------------------------------
// Cost calculation
// ---------------------------------------------------------------------------

export function calculateCost(
  modelId: string,
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_creation_input_tokens?: number;
    cache_read_input_tokens?: number;
  }
): number {
  const pricing = PRICING[modelId];
  if (!pricing) return 0;

  const perM = 1_000_000;
  const baseCacheWrite = usage.cache_creation_input_tokens ?? 0;
  const baseCacheRead = usage.cache_read_input_tokens ?? 0;
  // Non-cached input = total input minus cache hits
  const regularInput = Math.max(0, usage.input_tokens - baseCacheRead);

  return (
    (regularInput / perM) * pricing.input +
    (usage.output_tokens / perM) * pricing.output +
    (baseCacheWrite / perM) * pricing.cacheWrite +
    (baseCacheRead / perM) * pricing.cacheRead
  );
}

// ---------------------------------------------------------------------------
// Build usage from SDK response
// ---------------------------------------------------------------------------

function buildUsage(
  modelId: string,
  raw: { input_tokens: number; output_tokens: number; cache_creation_input_tokens?: number | null; cache_read_input_tokens?: number | null }
): TokenUsage {
  const cacheCreationInputTokens = raw.cache_creation_input_tokens ?? 0;
  const cacheReadInputTokens = raw.cache_read_input_tokens ?? 0;
  return {
    inputTokens: raw.input_tokens,
    outputTokens: raw.output_tokens,
    cacheCreationInputTokens,
    cacheReadInputTokens,
    cost: calculateCost(modelId, {
      input_tokens: raw.input_tokens,
      output_tokens: raw.output_tokens,
      cache_creation_input_tokens: cacheCreationInputTokens,
      cache_read_input_tokens: cacheReadInputTokens,
    }),
  };
}

// ---------------------------------------------------------------------------
// Resolve system param — needed because Anthropic SDK expects its own type
// for cacheable system messages
// ---------------------------------------------------------------------------

function resolveSystemParam(
  system: string | CacheableSystemMessage[]
): string | CacheableSystemMessage[] {
  if (typeof system === "string") return system;
  return system as CacheableSystemMessage[];
}

// ---------------------------------------------------------------------------
// Neo4j usage recording
// ---------------------------------------------------------------------------

async function recordUsage(
  modelId: string,
  usage: TokenUsage,
  contentId?: string
): Promise<void> {
  try {
    const driver = getDriver();
    const session = driver.session();
    try {
      const id = `ai-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      await session.run(
        `
        CREATE (a:AIUsage {
          id: $id,
          model: $model,
          inputTokens: $inputTokens,
          outputTokens: $outputTokens,
          cacheCreationInputTokens: $cacheCreation,
          cacheReadInputTokens: $cacheRead,
          cost: $cost,
          createdAt: datetime()
        })
        WITH a
        OPTIONAL MATCH (c:ContentPiece {id: $contentId})
        FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
          CREATE (c)-[:HAS_AI_USAGE]->(a)
        )
        `,
        {
          id,
          model: modelId,
          inputTokens: usage.inputTokens,
          outputTokens: usage.outputTokens,
          cacheCreation: usage.cacheCreationInputTokens,
          cacheRead: usage.cacheReadInputTokens,
          cost: usage.cost,
          contentId: contentId ?? "",
        }
      );
    } finally {
      await session.close();
    }
  } catch {
    // Usage recording is non-critical — don't fail the AI call
    console.error("[claude] Failed to record AI usage to Neo4j");
  }
}

// ---------------------------------------------------------------------------
// generateText
// ---------------------------------------------------------------------------

export async function generateText(
  params: GenerateTextParams
): Promise<GenerateTextResult> {
  const anthropic = getClient();
  const modelId = MODEL_MAP[params.model ?? "haiku"];

  const response = await anthropic.messages.create({
    model: modelId,
    max_tokens: params.maxTokens ?? 1024,
    temperature: params.temperature ?? 0.7,
    system: resolveSystemParam(params.system),
    messages: params.messages,
  });

  const text = response.content
    .filter((block): block is Anthropic.TextBlock => block.type === "text")
    .map((block) => block.text)
    .join("");

  const usage = buildUsage(modelId, response.usage);
  await recordUsage(modelId, usage, params.contentId);

  return { text, usage };
}

// ---------------------------------------------------------------------------
// generateStructured — returns parsed & validated output via Zod schema
// ---------------------------------------------------------------------------

export async function generateStructured<T extends z.ZodType>(
  params: GenerateStructuredParams<T>
): Promise<{ data: z.infer<T>; usage: TokenUsage }> {
  const anthropic = getClient();
  const modelId = MODEL_MAP[params.model ?? "haiku"];

  const response = await anthropic.messages.parse({
    model: modelId,
    max_tokens: params.maxTokens ?? 1024,
    temperature: params.temperature ?? 0.3,
    system: resolveSystemParam(params.system),
    messages: params.messages,
    output_config: {
      format: zodOutputFormat(params.schema),
    },
  });

  const data = response.parsed_output as z.infer<T>;
  const usage = buildUsage(modelId, response.usage);
  await recordUsage(modelId, usage, params.contentId);

  return { data, usage };
}
