---
name: nextjs-sanity-seo
description: >
  SEO implementation patterns for Next.js and Sanity CMS codebases. Use this skill when the user asks about
  "Next.js SEO", "Sanity SEO", "Next.js metadata", "generateMetadata", "Sanity schema for SEO",
  "structured data in Next.js", "JSON-LD in Next.js", "sitemap.ts", "robots.ts", "next/image SEO",
  "Sanity GROQ for SEO", "Open Graph in Next.js", "hreflang in Next.js", "canonical URLs in Next.js",
  "SEO component", "Sanity SEO fields", "portable text SEO", "image alt text from Sanity",
  "dynamic metadata from CMS", "CMS-driven SEO", "headless CMS SEO", "Next.js sitemap generation",
  "Sanity redirect management", "SEO audit of Next.js codebase", "fix SEO in my Next.js app",
  or any request involving implementing or fixing SEO in a Next.js + Sanity project.
  Also triggers on "audit my codebase for SEO issues", "SEO code review", or "implement SEO best practices in code".
---

# Next.js + Sanity SEO Implementation

Production-ready SEO implementation patterns for Next.js applications powered by Sanity CMS. Covers metadata, structured data, sitemaps, redirects, and performance optimization.

## Sanity Schema Patterns

### SEO Fields Object

Create a reusable SEO object type for all document types:

```typescript
// schemas/objects/seo.ts
import { defineType, defineField } from 'sanity'

export const seo = defineType({
  name: 'seo',
  title: 'SEO',
  type: 'object',
  fields: [
    defineField({
      name: 'title',
      title: 'SEO Title',
      type: 'string',
      description: 'Override the default title. 50-60 characters recommended.',
      validation: (Rule) => Rule.max(70).warning('Title should be under 60 characters for best results'),
    }),
    defineField({
      name: 'description',
      title: 'Meta Description',
      type: 'text',
      rows: 3,
      description: '150-160 characters recommended. Include a call to action.',
      validation: (Rule) => Rule.max(170).warning('Description should be under 160 characters'),
    }),
    defineField({
      name: 'image',
      title: 'Social Share Image',
      type: 'image',
      description: 'Recommended: 1200x630px. Used for Open Graph and Twitter cards.',
    }),
    defineField({
      name: 'noIndex',
      title: 'No Index',
      type: 'boolean',
      description: 'Prevent this page from appearing in search results',
      initialValue: false,
    }),
    defineField({
      name: 'canonicalUrl',
      title: 'Canonical URL',
      type: 'url',
      description: 'Only set if this content is syndicated from another source',
    }),
  ],
})
```

### Author Schema with E-E-A-T

```typescript
// schemas/documents/author.ts
export const author = defineType({
  name: 'author',
  type: 'document',
  fields: [
    defineField({ name: 'name', type: 'string' }),
    defineField({ name: 'slug', type: 'slug', options: { source: 'name' } }),
    defineField({ name: 'role', type: 'string' }),
    defineField({ name: 'bio', type: 'text' }),
    defineField({
      name: 'credentials',
      type: 'array',
      of: [{ type: 'string' }],
      description: 'Professional credentials, certifications, etc.',
    }),
    defineField({ name: 'image', type: 'image' }),
    defineField({
      name: 'sameAs',
      type: 'array',
      of: [{ type: 'url' }],
      description: 'LinkedIn, Twitter, personal site — used in Person schema.org markup',
    }),
  ],
})
```

### FAQ Schema for AEO

```typescript
// schemas/objects/faq.ts
export const faq = defineType({
  name: 'faq',
  type: 'object',
  fields: [
    defineField({ name: 'question', type: 'string' }),
    defineField({ name: 'answer', type: 'text' }),
  ],
})

// Add to page/post schemas:
defineField({
  name: 'faqs',
  type: 'array',
  of: [{ type: 'faq' }],
  description: 'FAQ section — generates FAQPage structured data for AI Overviews',
})
```

### Redirect Management

```typescript
// schemas/documents/redirect.ts
export const redirect = defineType({
  name: 'redirect',
  type: 'document',
  fields: [
    defineField({ name: 'source', type: 'string', description: 'Source path (e.g., /old-page)' }),
    defineField({ name: 'destination', type: 'string', description: 'Destination path or URL' }),
    defineField({ name: 'permanent', type: 'boolean', initialValue: true }),
    defineField({ name: 'isEnabled', type: 'boolean', initialValue: true }),
  ],
})
```

## Next.js Implementation

### Dynamic Metadata (App Router)

```typescript
// app/[slug]/page.tsx
import { Metadata } from 'next'
import { sanityFetch } from '@/sanity/lib/fetch'
import { urlFor } from '@/sanity/lib/image'

export async function generateMetadata({ params }): Promise<Metadata> {
  const { slug } = await params
  const { data } = await sanityFetch({
    query: PAGE_QUERY,
    params: { slug },
    stega: false, // Critical: disable stega in metadata
  })

  if (!data) return {}

  const title = data.seo?.title || data.title
  const description = data.seo?.description || data.excerpt

  return {
    title,
    description,
    robots: data.seo?.noIndex ? 'noindex, nofollow' : undefined,
    alternates: {
      canonical: data.seo?.canonicalUrl || `https://yourdomain.com/${slug}`,
    },
    openGraph: {
      title,
      description,
      type: 'article',
      url: `https://yourdomain.com/${slug}`,
      images: data.seo?.image ? [{
        url: urlFor(data.seo.image).width(1200).height(630).url(),
        width: 1200,
        height: 630,
        alt: data.title,
      }] : [],
      publishedTime: data.publishedAt,
      modifiedTime: data._updatedAt,
      authors: data.author?.name ? [data.author.name] : [],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
    },
  }
}
```

### Dynamic Sitemap

```typescript
// app/sitemap.ts
import { MetadataRoute } from 'next'
import { client } from '@/sanity/lib/client'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const pages = await client.fetch(`
    *[_type in ["page", "post", "service"] && defined(slug.current) && seo.noIndex != true]{
      "url": select(
        _type == "page" => "/" + slug.current,
        _type == "post" => "/blog/" + slug.current,
        _type == "service" => "/services/" + slug.current
      ),
      _updatedAt
    }
  `)

  return [
    { url: 'https://yourdomain.com', lastModified: new Date(), changeFrequency: 'weekly', priority: 1 },
    ...pages.map((page: any) => ({
      url: `https://yourdomain.com${page.url}`,
      lastModified: new Date(page._updatedAt),
    })),
  ]
}
```

### Robots.txt

```typescript
// app/robots.ts
import { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: '*', allow: '/', disallow: ['/api/', '/studio/'] },
      { userAgent: 'GPTBot', allow: '/' },
      { userAgent: 'ClaudeBot', allow: '/' },
      { userAgent: 'PerplexityBot', allow: '/' },
    ],
    sitemap: 'https://yourdomain.com/sitemap.xml',
  }
}
```

### JSON-LD Component

```typescript
// components/JsonLd.tsx
import { Thing, WithContext } from 'schema-dts'

export function JsonLd<T extends Thing>({ data }: { data: WithContext<T> }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  )
}
```

### CMS-Driven Redirects

```typescript
// next.config.ts
import { client } from './sanity/lib/client'

const nextConfig = {
  async redirects() {
    const redirects = await client.fetch(`
      *[_type == "redirect" && isEnabled == true]{
        source, destination, permanent
      }
    `)
    return redirects
  },
}
```

### Image Optimization

Always use `next/image` with Sanity URL builder:
```typescript
import Image from 'next/image'
import { urlFor } from '@/sanity/lib/image'

<Image
  src={urlFor(image).width(800).height(450).auto('format').url()}
  alt={image.alt || 'Descriptive fallback alt text'}
  width={800}
  height={450}
  loading={isAboveFold ? 'eager' : 'lazy'}
  placeholder="blur"
  blurDataURL={image.lqip}
/>
```

## Codebase Audit Checklist

When auditing a Next.js + Sanity codebase for SEO:

1. **Metadata** — Does every page type have `generateMetadata`? Is `stega: false` set?
2. **Sitemap** — Does `app/sitemap.ts` exist? Does it exclude noIndex pages?
3. **Robots** — Does `app/robots.ts` exist? Are AI crawlers configured?
4. **Structured Data** — Are JSON-LD components rendering on content pages?
5. **Images** — Are all images using `next/image`? Do they have alt text from CMS?
6. **Canonical URLs** — Are self-referencing canonicals set on every page?
7. **Redirects** — Is there a redirect management system?
8. **Performance** — Are fonts optimized? Is there code splitting? Are images sized correctly?
9. **SEO Schema Fields** — Does Sanity have reusable SEO object types?
10. **Author E-E-A-T** — Are author pages with credentials and structured data implemented?

## GROQ Patterns for SEO

```groq
// Full page with SEO fields
*[_type == "post" && slug.current == $slug][0]{
  title,
  slug,
  publishedAt,
  _updatedAt,
  "excerpt": pt::text(body[0..2]),
  seo,
  author->{
    name,
    slug,
    credentials,
    image,
    sameAs,
    bio
  },
  "faqs": faqs[]{question, answer},
  "headings": body[style in ["h2", "h3"]]{
    "text": pt::text(@),
    style
  }
}
```

## References

- **`references/nextjs-metadata-patterns.md`** — Advanced metadata patterns
- **`references/sanity-seo-schemas.md`** — Complete Sanity schema collection for SEO
- **`references/structured-data-nextjs.md`** — JSON-LD implementation patterns
