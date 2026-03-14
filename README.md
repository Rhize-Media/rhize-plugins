# Rhize Plugins

A curated collection of Claude plugins by [Rhize Media](https://rhize.media) — web development, SEO, AI, and marketing tools for Cowork and Claude Code.

## Available Plugins

| Plugin | Description |
|--------|-------------|
| [seo-aeo-geo](./seo-aeo-geo) | Comprehensive SEO, AEO, and GEO auditing powered by DataForSEO API with Next.js + Sanity CMS best practices |

## Installation

Add this marketplace in Cowork via **Settings > Plugins > Add Marketplace** using the repository URL:

```
https://github.com/Rhize-Media/rhize-plugins
```

All plugins in this repo will become available for installation.

## Plugin Setup

Each plugin may require its own environment variables or MCP server credentials. Check the plugin's `README.md` and `.env.example` for setup instructions.

### DataForSEO Credentials (for seo-aeo-geo)

Add to your `~/.zshrc`:

```bash
export DATAFORSEO_USERNAME="your_email"
export DATAFORSEO_PASSWORD="your_api_password"
```

## Contributing

To add a new plugin, create a subdirectory with the standard plugin structure:

```
your-plugin-name/
├── .claude-plugin/
│   └── plugin.json
├── .mcp.json          (optional — if the plugin needs an MCP server)
├── skills/
│   └── your-skill/
│       └── SKILL.md
├── commands/
│   └── your-command.md
├── hooks/             (optional)
└── README.md
```

## License

Proprietary — Rhize Media. All rights reserved.
