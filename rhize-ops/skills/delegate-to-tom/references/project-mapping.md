# Jira Project Mapping Guide

Use this reference to determine which Jira project a delegated task belongs to. When Jim doesn't specify, infer from context using these heuristics.

## Project Directory

### Client Projects (Website/Dev Work)
| Key | Name | Typical Tasks |
|-----|------|---------------|
| CPT | CP Triangle | Website updates, dev work |
| FEN | Fenefab | Website updates, dev work |
| GH | Glenwood Homes | Website updates, dev work |
| SGD | SJ Glass & Door | Website updates, dev work |
| SUM | Summit Exteriors | Website updates, dev work |
| VBA | vba-hoops | Website updates (uses Payload CMS, not Sanity) |
| WAN | Wanderhome | Website updates, dev work |
| WH2 | Wanderhome-V2 | Website updates, dev work |
| ED | Elev8 Distribution | Business tasks |

### Internal Rhize Media Projects
| Key | Name | Typical Tasks |
|-----|------|---------------|
| RHIZE | Rhize Media | Internal dev, tooling, infrastructure |
| RMM | Rhize Marketing | Marketing campaigns, content, ads, SEO |
| RSA | Rhize SuperObsidian App | Obsidian-related dev work |
| GAI | GHL AI Assistant | AI assistant development |
### Service Projects
| Key | Name | Typical Tasks |
|-----|------|---------------|
| SJGS | SJ Glass Services | Service desk, client support requests |

## Inference Rules

When Jim doesn't name a project explicitly:
1. **Marketing/SEO/Ads tasks** → default to `RMM` (Rhize Marketing)
2. **Client website updates** → match by client name to the project above
3. **Internal tooling or Rhize Media work** → `RHIZE`
4. **Obsidian/plugin work** → `RSA`
5. **If ambiguous** → ask Jim to clarify