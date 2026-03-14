# AI Crawler Directives

Complete robots.txt configurations for managing AI crawler access.

## Known AI Crawlers

| Crawler | Operator | Purpose | User-Agent String |
|---------|----------|---------|------------------|
| GPTBot | OpenAI | Training + browsing | `GPTBot` |
| ChatGPT-User | OpenAI | Real-time browsing | `ChatGPT-User` |
| ClaudeBot | Anthropic | Training | `ClaudeBot` |
| PerplexityBot | Perplexity | Search indexing | `PerplexityBot` |
| Google-Extended | Google | AI training (Gemini) | `Google-Extended` |
| Googlebot | Google | Search indexing | `Googlebot` |
| Bingbot | Microsoft | Search indexing | `Bingbot` |
| Applebot-Extended | Apple | AI features | `Applebot-Extended` |
| Bytespider | ByteDance | Training | `Bytespider` |
| CCBot | Common Crawl | Training data | `CCBot` |
| FacebookExternalHit | Meta | Link previews | `facebookexternalhit` |

## Configuration Strategies

### Maximum AI Visibility (Recommended for most sites)
Allow all AI crawlers to maximize citation opportunities:

```
User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Applebot-Extended
Allow: /
```

### Selective AI Access
Allow browsing/search bots but block training-only crawlers:

```
# Allow real-time search/browsing bots
User-agent: ChatGPT-User
Allow: /

User-agent: PerplexityBot
Allow: /

# Block training-only crawlers
User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: Bytespider
Disallow: /
```

### Block All AI Crawlers
Not recommended — reduces AI visibility significantly:

```
User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: PerplexityBot
Disallow: /

User-agent: Google-Extended
Disallow: /
```

## Important Notes

- **Google-Extended** only controls AI training use. Blocking it does NOT affect Google Search indexing (that's Googlebot).
- **ChatGPT-User** is the browsing agent; blocking it prevents ChatGPT from reading your pages in real-time but GPTBot handles training.
- Review your AI crawler policy **quarterly** — this landscape changes rapidly.
- Blocking AI crawlers prevents training use but may also reduce AI citations.
- There is no standard way to allow citation but block training — it's currently all or nothing per crawler.

## Next.js Implementation

```typescript
// app/robots.ts
import { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/studio/', '/admin/'],
      },
      // AI Crawlers — Maximum Visibility Strategy
      { userAgent: 'GPTBot', allow: '/' },
      { userAgent: 'ChatGPT-User', allow: '/' },
      { userAgent: 'ClaudeBot', allow: '/' },
      { userAgent: 'PerplexityBot', allow: '/' },
      { userAgent: 'Google-Extended', allow: '/' },
      { userAgent: 'Applebot-Extended', allow: '/' },
    ],
    sitemap: 'https://yourdomain.com/sitemap.xml',
  }
}
```
