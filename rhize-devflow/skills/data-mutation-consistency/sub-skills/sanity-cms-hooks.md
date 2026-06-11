# Sanity CMS Mutations Sub-Skill

> **Data mutation consistency patterns for `@sanity/client` operations**

## Metadata

| Property | Value |
|----------|-------|
| Version | 2.0.0 |
| Created | 2024-12-13 |
| Updated | 2024-12-14 |
| Parent Skill | data-mutation-consistency |
| Detection | `@sanity/client` or `next-sanity` in package.json |
| Scope | CMS operations, real-time subscriptions, cache invalidation |

---

## Overview

This sub-skill enforces consistent mutation patterns when using Sanity's Content Lake via `@sanity/client` or `next-sanity`. Patterns are validated against the latest Sanity documentation (next-sanity v11+, December 2024).

```
┌─────────────────────────────────────────────────────────────────┐
│                 SANITY MUTATION ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Frontend (Next.js App Router)                                  │
│  ├── defineLive() ────────────► Live Content API                │
│  │   └── Auto-revalidation      (Real-time subscriptions)       │
│  │                                                              │
│  ├── client.create() ─────────► Content Lake                    │
│  ├── client.patch() ──────────► (Direct Mutations)              │
│  └── client.delete() ─────────►                                 │
│                                                                  │
│  Cache Layers                                                   │
│  ├── Sanity CDN (useCdn: true) ─► Fast, eventually consistent   │
│  ├── Next.js Cache ────────────► Tag-based revalidation         │
│  └── Webhooks ─────────────────► On-demand invalidation         │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  RECOMMENDED APPROACH (next-sanity v11+)                         │
│  └── defineLive() + SanityLive component = Zero-config live     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Patterns

### 1. Client Configuration (Validated December 2024)

```typescript
// src/sanity/lib/client.ts
import { createClient } from 'next-sanity'

// Base client - useCdn: true is the recommended default
export const client = createClient({
  projectId: process.env.NEXT_PUBLIC_SANITY_PROJECT_ID!,
  dataset: process.env.NEXT_PUBLIC_SANITY_DATASET!,
  apiVersion: 'v2025-03-04',  // Latest API version
  useCdn: true,               // ✅ RECOMMENDED: CDN for reads
  stega: {
    studioUrl: process.env.NEXT_PUBLIC_SANITY_STUDIO_URL,
  },
})
```

**CDN Usage Rules (from official docs):**
- `useCdn: true` → Default for all reads, fast responses
- `useCdn: false` → Only for: ISR webhooks, generateStaticParams, draft mode
- CDN cache flushes on every publish mutation


### 2. Live Content API (Recommended Approach - v11+)

```typescript
// src/sanity/lib/live.ts
import { defineLive } from 'next-sanity/live'  // ✅ v11+ path
import { client } from './client'

const token = process.env.SANITY_API_READ_TOKEN
if (!token) {
  throw new Error('Missing SANITY_API_READ_TOKEN')
}

export const { sanityFetch, SanityLive } = defineLive({
  client: client.withConfig({ apiVersion: 'v2025-03-04' }),
  serverToken: token,
  browserToken: token,  // Same token OK - only shared when draft mode enabled
})
```

```typescript
// src/app/layout.tsx
import { SanityLive } from '@/sanity/lib/live'
import { VisualEditing } from 'next-sanity/visual-editing'
import { draftMode } from 'next/headers'

export default async function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        {children}
        <SanityLive />
        {(await draftMode()).isEnabled && <VisualEditing />}
      </body>
    </html>
  )
}
```

**Benefits of defineLive:**
- Zero-config automatic revalidation
- Real-time updates for draft AND published content
- Proper draft mode integration
- CDN-optimized for published content


### 3. Preview/Draft Client Configuration

```typescript
// src/sanity/lib/preview-client.ts
import { createClient } from 'next-sanity'

// Preview client for draft content
export const previewClient = createClient({
  projectId: process.env.NEXT_PUBLIC_SANITY_PROJECT_ID!,
  dataset: process.env.NEXT_PUBLIC_SANITY_DATASET!,
  apiVersion: 'v2025-03-04',
  useCdn: false,              // ✅ REQUIRED for drafts
  perspective: 'drafts',      // ✅ Modern (replaces 'previewDrafts' and 'raw')
  token: process.env.SANITY_API_READ_TOKEN,
})

// ❌ DEPRECATED patterns:
// perspective: 'raw'           // Old default, returns both draft and published
// perspective: 'previewDrafts' // Old name, use 'drafts' instead
```

**Perspective Options (API v2025-02-19+):**
- `published` → Default, no drafts (production)
- `drafts` → Prioritizes drafts over published (preview mode)
- `raw` → Returns both drafts and published (legacy)


### 4. Manual Fetch Helper (Alternative to defineLive)

For projects not using Live Content API, use a centralized fetch helper:

```typescript
// src/sanity/lib/fetch.ts
import 'server-only'
import { client } from './client'
import { type QueryParams } from 'next-sanity'
import * as Sentry from '@sentry/nextjs'  // ✅ Production error tracking

type SanityFetchOptions<T> = {
  query: string
  params?: QueryParams
  tags?: string[]
  revalidate?: number | false
}

/**
 * Centralized Sanity fetch with error handling and caching
 */
export async function sanityFetch<T>({
  query,
  params = {},
  tags = [],
  revalidate = 3600,  // 1 hour default
}: SanityFetchOptions<T>): Promise<T | null> {
  try {
    return await client.fetch<T>(query, params, {
      next: {
        revalidate: tags.length ? false : revalidate,
        tags,
      },
    })
  } catch (error) {
    // ✅ Production pattern: Sentry + graceful fallback
    captureSanityError(error, 'sanityFetch', { query: query.slice(0, 100), params })
    return null  // Graceful degradation
  }
}

/**
 * Capture Sanity errors to Sentry with consistent context
 */
function captureSanityError(
  error: unknown,
  functionName: string,
  params?: Record<string, unknown>
): void {
  Sentry.captureException(error, {
    tags: {
      'sanity.function': functionName,
      'sanity.error': 'fetch_failed',
    },
    extra: {
      functionName,
      params,
      errorMessage: error instanceof Error ? error.message : String(error),
    },
  })
  console.error(`[SanityClient.${functionName}] Fetch error:`, error)
}
```


### 5. Write Client (Server-Side Only)

```typescript
// src/sanity/lib/write-client.ts
import 'server-only'
import { createClient } from '@sanity/client'

export const writeClient = createClient({
  projectId: process.env.NEXT_PUBLIC_SANITY_PROJECT_ID!,
  dataset: process.env.NEXT_PUBLIC_SANITY_DATASET!,
  apiVersion: 'v2025-03-04',
  useCdn: false,  // Never CDN for mutations
  token: process.env.SANITY_API_WRITE_TOKEN,
})
```

### 6. Document Creation

```typescript
// ✅ Correct: Create with explicit structure
async function createPost(data: CreatePostInput) {
  const doc = await writeClient.create({
    _type: 'post',
    title: data.title,
    slug: { _type: 'slug', current: slugify(data.title) },
    author: { _type: 'reference', _ref: data.authorId },
    publishedAt: new Date().toISOString(),
  })
  
  revalidateTag('post')  // Trigger cache invalidation
  return doc
}

// ❌ Wrong: Missing _type in nested objects
async function createPostBad(data: CreatePostInput) {
  return writeClient.create({
    _type: 'post',
    slug: data.slug,  // Missing { _type: 'slug', current: ... }
    author: data.authorId,  // Missing { _type: 'reference', _ref: ... }
  })
}
```


### 7. Patch Operations

```typescript
// ✅ Correct: Atomic patch with setIfMissing
async function publishPost(postId: string) {
  return writeClient
    .patch(postId)
    .set({ published: true, publishedAt: new Date().toISOString() })
    .setIfMissing({ firstPublishedAt: new Date().toISOString() })
    .commit()
}

// ✅ Correct: Array operations
async function addTag(postId: string, tag: string) {
  return writeClient
    .patch(postId)
    .insert('after', 'tags[-1]', [{ _type: 'tag', _key: nanoid(), label: tag }])
    .commit()
}

// ✅ Correct: Increment/Decrement
async function incrementViews(postId: string) {
  return writeClient
    .patch(postId)
    .inc({ viewCount: 1 })
    .commit()
}

// ❌ Wrong: Missing _key in array items
async function addTagBad(postId: string, tag: string) {
  return writeClient
    .patch(postId)
    .insert('after', 'tags[-1]', [{ label: tag }])  // Missing _key!
    .commit()
}
```

### 8. Transactions (Atomic Multi-Document Operations)

```typescript
// ✅ Correct: Atomic transaction for related documents
async function createPostWithAuthor(data: CreatePostWithAuthorInput) {
  const authorId = `author-${nanoid()}`
  const postId = `post-${nanoid()}`
  
  const transaction = writeClient.transaction()
  
  transaction.create({
    _id: authorId,
    _type: 'author',
    name: data.authorName,
    email: data.authorEmail,
  })
  
  transaction.create({
    _id: postId,
    _type: 'post',
    title: data.title,
    author: { _type: 'reference', _ref: authorId },
  })
  
  const result = await transaction.commit()
  
  // Revalidate both caches
  revalidateTag('post')
  revalidateTag('author')
  
  return result
}
```


---

## Cache Invalidation Patterns

### 9. Webhook-Based Revalidation (Production Pattern)

```typescript
// src/app/api/sanity-webhook/route.ts
import { revalidatePath, revalidateTag } from 'next/cache'
import { type NextRequest, NextResponse } from 'next/server'
import { parseBody } from 'next-sanity/webhook'
import * as Sentry from '@sentry/nextjs'

// Type definitions for webhook payload
type WebhookPayload = {
  _type: string
  _id: string
  slug?: { current: string }
}

// Secret from Sanity webhook configuration
const WEBHOOK_SECRET = process.env.SANITY_WEBHOOK_SECRET

export async function POST(req: NextRequest) {
  try {
    // Validate webhook signature
    const { isValidSignature, body } = await parseBody<WebhookPayload>(
      req,
      WEBHOOK_SECRET
    )

    if (!isValidSignature) {
      return NextResponse.json(
        { message: 'Invalid signature' },
        { status: 401 }
      )
    }

    if (!body?._type) {
      return NextResponse.json(
        { message: 'Missing document type' },
        { status: 400 }
      )
    }

    // Type-based tag revalidation
    const results: Array<{ tag?: string; path?: string; success: boolean }> = []
    
    // Always revalidate the document type tag
    revalidateTag(body._type)
    results.push({ tag: body._type, success: true })

    // Type-specific revalidation
    switch (body._type) {
      case 'post':
        revalidateTag('post')
        if (body.slug?.current) {
          revalidatePath(`/blog/${body.slug.current}`)
          results.push({ path: `/blog/${body.slug.current}`, success: true })
        }
        revalidatePath('/blog')
        results.push({ path: '/blog', success: true })
        break

      case 'author':
        revalidateTag('author')
        revalidateTag('post')  // Posts display author info
        break

      case 'settings':
        revalidateTag('settings')
        revalidatePath('/', 'layout')  // Settings affect entire site
        break
    }

    // Return 207 Multi-Status for detailed results
    return NextResponse.json(
      { revalidated: true, results },
      { status: 207 }
    )

  } catch (error) {
    Sentry.captureException(error, {
      tags: { 'sanity.webhook': 'revalidation_failed' },
    })
    return NextResponse.json(
      { message: 'Error processing webhook' },
      { status: 500 }
    )
  }
}
```


### 10. Real-Time Subscriptions (Listen API)

```typescript
// For client-side real-time updates (when not using defineLive)
import { client } from '@/sanity/lib/client'

// Subscribe to document changes
const subscription = client
  .listen('*[_type == "post" && _id == $id]', { id: postId })
  .subscribe({
    next: (update) => {
      if (update.type === 'mutation') {
        // Handle document update
        console.log('Document updated:', update.result)
      }
    },
    error: (err) => {
      console.error('Subscription error:', err)
    },
  })

// Clean up on unmount
// subscription.unsubscribe()
```

---

## Utility Patterns

### 11. Video Asset URL Builder

```typescript
// Helper for video file URLs (from SJG project pattern)
const SANITY_CDN_URL = `https://cdn.sanity.io/files/${process.env.NEXT_PUBLIC_SANITY_PROJECT_ID}/${process.env.NEXT_PUBLIC_SANITY_DATASET}`

export function getSanityVideoFileUrl(assetRef: string): string {
  // assetRef format: "file-<id>-<extension>"
  const [, id, extension] = assetRef.split('-')
  return `${SANITY_CDN_URL}/${id}.${extension}`
}

// Usage in GROQ query:
// "videoUrl": video.asset._ref
// Then: getSanityVideoFileUrl(post.videoUrl)
```

### 12. Graceful Error Fallbacks

```typescript
// Pattern for safe data fetching with fallbacks
export async function getPostsWithFallback(): Promise<Post[]> {
  try {
    const posts = await sanityFetch<Post[]>({
      query: POSTS_QUERY,
      tags: ['post'],
    })
    return posts ?? []  // Graceful fallback to empty array
  } catch (error) {
    captureSanityError(error, 'getPostsWithFallback')
    return []  // App continues functioning
  }
}

export async function getPostBySlug(slug: string): Promise<Post | null> {
  try {
    return await sanityFetch<Post | null>({
      query: POST_BY_SLUG_QUERY,
      params: { slug },
      tags: [`post-${slug}`],
    })
  } catch (error) {
    captureSanityError(error, 'getPostBySlug', { slug })
    return null  // Graceful fallback
  }
}
```


---

## Consistency Scoring

Rate Sanity mutation implementations on a 1-10 scale:

| Score | Criteria |
|-------|----------|
| 10 | defineLive + SanityLive component, Sentry error tracking, graceful fallbacks |
| 9 | Manual sanityFetch helper with proper cache configuration, webhook revalidation |
| 8 | Tag-based caching with proper revalidation, error handling |
| 7 | Time-based caching, basic error handling |
| 6 | Direct client.fetch without cache configuration |
| 5 | Missing error handling or cache strategy |
| 4 | useCdn: false without valid reason |
| 3 | No cache invalidation strategy |
| 2 | Inline queries without defineQuery |
| 1 | Mutations without transactions where needed |

**Threshold:** Implementations scoring < 9 should trigger improvement warnings.

---

## Quick Reference

### Import Paths (next-sanity v11+)

```typescript
// Client creation
import { createClient } from 'next-sanity'

// Live Content API (recommended)
import { defineLive } from 'next-sanity/live'

// Visual Editing
import { VisualEditing } from 'next-sanity/visual-editing'

// Query definition (for TypeGen)
import { defineQuery } from 'next-sanity'

// Draft mode helpers
import { defineEnableDraftMode } from 'next-sanity/draft-mode'

// Webhook parsing
import { parseBody } from 'next-sanity/webhook'

// Write operations (server-only)
import { createClient } from '@sanity/client'
```

### Environment Variables

```bash
# Public (exposed to browser)
NEXT_PUBLIC_SANITY_PROJECT_ID=your-project-id
NEXT_PUBLIC_SANITY_DATASET=production
NEXT_PUBLIC_SANITY_STUDIO_URL=/studio

# Server-only
SANITY_API_READ_TOKEN=sk...    # Viewer role (for defineLive)
SANITY_API_WRITE_TOKEN=sk...   # Editor role (for mutations)
SANITY_WEBHOOK_SECRET=...      # Webhook signature validation
```


### Anti-Patterns to Avoid

```typescript
// ❌ WRONG: useCdn: false without valid reason
const client = createClient({
  useCdn: false,  // Only use false for SSG, ISR webhooks, or draft mode
})

// ❌ WRONG: perspective: 'raw' (deprecated)
const previewClient = createClient({
  perspective: 'raw',  // Use 'drafts' instead
})

// ❌ WRONG: Missing cache configuration in Next.js 15
const data = await client.fetch(query)  // No cache options!

// ✅ CORRECT: Explicit cache configuration
const data = await client.fetch(query, params, {
  cache: 'force-cache',  // Required in Next.js 15
  next: { tags: ['post'] },
})

// ❌ WRONG: Inline queries (no TypeGen support)
const posts = await client.fetch(`*[_type == "post"]`)

// ✅ CORRECT: defineQuery wrapper
const POSTS_QUERY = defineQuery(`*[_type == "post"]`)
const posts = await client.fetch(POSTS_QUERY)

// ❌ WRONG: Spread operator in GROQ (returns all fields)
const query = `*[_type == "post"]{...}`

// ✅ CORRECT: Explicit field projection
const query = `*[_type == "post"]{_id, title, slug, author->}`
```

---

## Migration Notes

### From Manual Fetch to defineLive

```typescript
// BEFORE (manual helper)
export async function sanityFetch<T>(options) {
  return client.fetch(options.query, options.params, {
    next: { tags: options.tags },
  })
}

// AFTER (defineLive)
import { defineLive } from 'next-sanity/live'

export const { sanityFetch, SanityLive } = defineLive({
  client,
  serverToken: process.env.SANITY_API_READ_TOKEN!,
  browserToken: process.env.SANITY_API_READ_TOKEN!,
})

// Don't forget to add <SanityLive /> to your root layout!
```

### From perspective: 'raw' to 'drafts'

```typescript
// BEFORE (deprecated)
const previewClient = client.withConfig({
  perspective: 'raw',
  useCdn: false,
  token: process.env.SANITY_TOKEN,
})

// AFTER (current)
const previewClient = client.withConfig({
  perspective: 'drafts',  // or 'previewDrafts' (both work)
  useCdn: false,
  token: process.env.SANITY_API_READ_TOKEN,
})
```

---

## Checklist

Before deploying Sanity integrations, verify:

- [ ] Using `defineLive` or manual fetch helper with proper caching
- [ ] `useCdn: true` for production reads (false only for SSG/ISR/draft)
- [ ] `cache: 'force-cache'` set explicitly (required in Next.js 15)
- [ ] All queries wrapped in `defineQuery()` for TypeGen
- [ ] Webhook handler validates signatures with `parseBody()`
- [ ] Tag-based revalidation configured for all content types
- [ ] Sentry error tracking with `captureSanityError()` helper
- [ ] Graceful fallbacks (return `[]`, `null`, `0` on errors)
- [ ] Write operations use server-only client with write token
- [ ] Transactions used for multi-document atomic operations
- [ ] `<SanityLive />` component in root layout (if using defineLive)
- [ ] Preview client uses `perspective: 'drafts'` (not 'raw')
