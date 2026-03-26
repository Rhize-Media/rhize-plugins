# Interview Question Bank

Categorized questions for Phase 2 requirements interviews. Select questions based on project type — don't ask everything, only what's relevant and not already answered by Phase 1 research.

## Architecture & Infrastructure

1. Should this be multi-tenant (serving multiple clients) or single-tenant?
2. What's the primary runtime? (n8n Cloud, self-hosted n8n, Node.js, Python, serverless)
3. Are there existing services or workflows this needs to integrate with?
4. What's the deployment target? (Vercel, n8n Cloud, Docker, AWS, etc.)
5. Do you have existing credentials/accounts for the required services?

## Input Sources

6. What types of content or data will feed into this system? (RSS, email, API, manual, webhooks)
7. For each input source: what format? How frequently? How much volume?
8. Should inputs be processed in real-time or batched on a schedule?
9. Are there specific sources to start with? (e.g., "Search Engine Journal RSS feed")
10. Should the system accept manual submissions? Through what interface?

## Processing & Transformation

11. What AI models should be used for processing? (Claude, Gemini, GPT, local models)
12. Should there be embedding/deduplication to avoid processing the same content twice?
13. What external APIs are needed for enrichment or analysis? (DataForSEO, Clearbit, etc.)
14. Should bulk API endpoints be preferred over individual calls for cost optimization?
15. What caching strategy makes sense? (TTL-based, content-hash, manual invalidation)

## Output & Distribution

16. Where does the final output go? (CMS, Google Sheets, database, API, files)
17. Which CMS? (Sanity, WordPress, Contentful, headless) What's the schema like?
18. Should content be "chopped" into shorter formats? For which platforms?
19. Which social platforms? (Instagram, LinkedIn, Twitter/X, Facebook, YouTube, TikTok)
20. What posting tool? (GHL Social Media Module, Buffer, native APIs, Hootsuite)

## Human Gates & Approval

21. Where should humans review before the system proceeds? (every step? key milestones only?)
22. What's the approval interface? (Google Sheets status column, Slack buttons, email, custom UI)
23. Should there be dual-trigger approval? (e.g., both Sheets edit AND Slack button)
24. Who approves? (you only? client contacts? team members?)
25. What happens if no one approves within X hours/days? (timeout, escalation, auto-reject)

## Error Handling & Monitoring

26. What's the error notification channel? (Slack, email, PagerDuty, Sentry)
27. Should failed items be automatically retried? How many times? With what backoff?
28. Should there be a dedicated error-tracking project in Sentry?
29. What monitoring cadence makes sense? (real-time alerts, daily digest, weekly summary)
30. For content monitoring: should there be a separate optimization/refinement workflow?

## Multi-Tenancy (if applicable)

31. How many tenants/clients initially? Growth trajectory?
32. Should each tenant have isolated data storage? (separate workbooks, databases, etc.)
33. Per-tenant configuration: what varies? (brand voice, API keys, schema mappings, connected platforms)
34. Should onboarding a new tenant be automated or manual?
35. Is there a master registry that lists all tenants and their config?

## Content-Specific (if content project)

36. What's the target content cadence? (1 article/week, daily posts, etc.)
37. Should articles include structured data (JSON-LD)? Which schema types?
38. Is SEO/AEO/GEO optimization a priority? Which aspects?
39. Should content be validated against brand voice guidelines?
40. What analytics should be tracked? (PostHog events, UTM parameters, conversion tracking)

## Web Applications (if web app project)

41. What's the frontend framework? (Next.js, Nuxt, SvelteKit, Astro, etc.)
42. SSR, SSG, or hybrid rendering strategy?
43. What authentication approach? (Clerk, Auth0, NextAuth, custom)
44. What CMS for content? (Sanity, Contentful, WordPress, none)
45. Deployment target? (Vercel, Netlify, AWS, self-hosted)
46. SEO requirements? (structured data, sitemap, robots.txt, meta tags)
47. Analytics stack? (PostHog, GA4, Plausible, Mixpanel)
48. Design system or component library? (shadcn/ui, Tailwind, MUI, custom)
49. Accessibility requirements? (WCAG 2.1 AA, specific audit needs)
50. Performance budget? (Core Web Vitals targets, bundle size limits)

## Integration Projects (if integration project)

51. What systems are being connected? (API endpoints, protocols)
52. Sync frequency? (real-time webhooks, polling interval, batch schedule)
53. Data mapping: how do fields correspond between systems?
54. Conflict resolution strategy? (last-write-wins, merge, manual review)
55. Idempotency requirements? (safe to retry without side effects?)
56. Rate limits on target APIs? Throttling or queuing strategy?
57. Data validation at ingress? (schema validation, type coercion, rejection rules)
58. Historical data migration needed? (backfill existing records)
59. Monitoring: how do you know if sync is healthy? (lag metrics, error rates)
60. Rollback strategy if a sync introduces bad data?

## Scope & Constraints

61. What's explicitly OUT of scope for v1?
62. Budget constraints? (API costs, hosting, tool subscriptions)
63. Timeline? (when do you want the first working workflow?)
64. Are there any compliance or regulatory requirements?
65. What's the definition of "done" for this project?
