# Sentry Configuration

## Next.js File Locations

In Next.js projects, Sentry initialization happens in specific files:

| File | Purpose |
|------|---------|
| `instrumentation-client.(js\|ts)` | Client-side initialization |
| `sentry.server.config.ts` | Server-side initialization |
| `sentry.edge.config.ts` | Edge runtime initialization |

**Important:** Initialization only needs to happen in these files. Other files should import Sentry functionality with:
```typescript
import * as Sentry from "@sentry/nextjs";
```

## Baseline Configuration

```typescript
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: "https://your-dsn@sentry.io/project-id",
  enableLogs: true,
});
```

## Configuration with Console Integration

To automatically capture console logs as Sentry logs:

```typescript
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: "https://your-dsn@sentry.io/project-id",
  enableLogs: true,
  integrations: [
    // Send console.log, console.warn, and console.error as logs to Sentry
    Sentry.consoleLoggingIntegration({ levels: ["log", "warn", "error"] }),
  ],
});
```

## Environment-Specific Configuration

```typescript
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  enableLogs: true,
  environment: process.env.NODE_ENV,

  // Only enable in production
  enabled: process.env.NODE_ENV === "production",

  // Sample rate for performance monitoring
  tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,
});
```

## Common Configuration Options

| Option | Purpose | Default |
|--------|---------|---------|
| `dsn` | Project identifier | Required |
| `enableLogs` | Enable structured logging | `false` |
| `environment` | Environment name | `production` |
| `tracesSampleRate` | % of transactions to trace | `1.0` |
| `enabled` | Enable/disable SDK | `true` |
