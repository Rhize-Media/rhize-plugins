# Sentry Structured Logging

## Setup Requirements

1. Enable logging in Sentry initialization:
   ```typescript
   Sentry.init({ enableLogs: true });
   ```

2. Import and reference the logger:
   ```typescript
   import * as Sentry from "@sentry/nextjs";
   const { logger } = Sentry;
   ```

## Log Levels

| Level | Method | Use Case |
|-------|--------|----------|
| `trace` | `logger.trace()` | Detailed debugging, function entry/exit |
| `debug` | `logger.debug()` | Development debugging, cache operations |
| `info` | `logger.info()` | Normal operations, state changes |
| `warn` | `logger.warn()` | Potential issues, rate limits, deprecations |
| `error` | `logger.error()` | Operation failures, handled errors |
| `fatal` | `logger.fatal()` | Critical system failures |

## Usage Patterns

### Basic Logging with Attributes

```typescript
const { logger } = Sentry;

// Trace - detailed debugging
logger.trace("Starting database connection", { database: "users" });

// Debug - use logger.fmt for template literals
logger.debug(logger.fmt`Cache miss for user: ${userId}`);

// Info - normal operations
logger.info("Updated profile", { profileId: 345 });

// Warn - potential issues
logger.warn("Rate limit reached for endpoint", {
  endpoint: "/api/results/",
  isEnterprise: false,
});

// Error - operation failures
logger.error("Failed to process payment", {
  orderId: "order_123",
  amount: 99.99,
});

// Fatal - critical failures
logger.fatal("Database connection pool exhausted", {
  database: "users",
  activeConnections: 100,
});
```

### Using `logger.fmt` Template Literal

`logger.fmt` is a template literal function for structured logs with interpolated variables:

```typescript
const userId = "user_123";
const orderId = "order_456";

// Variables are properly structured in the log
logger.debug(logger.fmt`Processing order ${orderId} for user ${userId}`);

// Equivalent to:
// logger.debug("Processing order order_456 for user user_123")
// But with better variable extraction for search/filter
```

## Automatic Console Capture

Use `consoleLoggingIntegration` to automatically capture console methods:

```typescript
Sentry.init({
  dsn: "...",
  enableLogs: true,
  integrations: [
    Sentry.consoleLoggingIntegration({
      levels: ["log", "warn", "error"]
    }),
  ],
});
```

This captures `console.log()`, `console.warn()`, and `console.error()` calls automatically.

## Best Practices

1. **Consistent Context**: Always include relevant IDs and identifiers
   ```typescript
   logger.info("Order created", {
     orderId,
     userId,
     itemCount: items.length
   });
   ```

2. **Appropriate Levels**: Match severity to log level
   - `trace`/`debug`: Only useful during development
   - `info`: Successful operations worth tracking
   - `warn`: Issues that don't stop execution
   - `error`/`fatal`: Failures requiring attention

3. **Structured Attributes**: Use objects for searchable fields
   ```typescript
   // Good - searchable attributes
   logger.error("Payment failed", { orderId, errorCode: "DECLINED" });

   // Avoid - information buried in message
   logger.error(`Payment failed for order ${orderId}: DECLINED`);
   ```

4. **Avoid Sensitive Data**: Never log passwords, tokens, or PII
   ```typescript
   // Good
   logger.info("User authenticated", { userId: user.id });

   // Bad - leaking sensitive data
   logger.info("User authenticated", { email: user.email, token });
   ```
