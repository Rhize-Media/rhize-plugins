---
name: sentry-instrumentation
tier: custom
domain: sentry
maturity: stable
description: >-
  Rhize conventions for instrumenting Next.js/TypeScript code with Sentry — exception capture
  (captureException), custom performance spans (startSpan), and structured logging (logger.fmt).
  Use when the user wants to "add Sentry", "capture exception", "add tracing/spans", "instrument"
  an API call or user interaction, or "set up structured logging" in app code. This is the
  write-the-code companion to error-lifecycle-management (which handles triage/RCA); for full
  per-framework SDK setup defer to the official sentry:* developer-kit skills and keep this for
  Rhize house patterns.
version: 1.0.0
---

## Overview
This skill provides patterns and guidance for instrumenting applications with Sentry. It covers three core areas: exception catching, performance tracing with custom spans, and structured logging. These patterns ensure consistent observability across the codebase.

## Triggers
**Keywords:** sentry, error tracking, tracing, spans, logging, observability, monitoring, captureException, startSpan, logger
**Scenarios:** Adding error tracking, implementing performance monitoring, setting up structured logging, instrumenting API calls, tracking user interactions

## Quick Start

### Exception Catching
Use `Sentry.captureException(error)` in try-catch blocks:
```typescript
try {
  await riskyOperation();
} catch (error) {
  Sentry.captureException(error);
  // Handle error appropriately
}
```

### Custom Spans
Wrap meaningful actions with `Sentry.startSpan`:
```typescript
Sentry.startSpan(
  { op: "ui.click", name: "Submit Form" },
  (span) => {
    span.setAttribute("formId", formId);
    submitForm();
  }
);
```

### Structured Logging
Use `logger.fmt` for template literals with variables:
```typescript
const { logger } = Sentry;
logger.info("User action completed", { userId: 123, action: "checkout" });
logger.debug(logger.fmt`Processing order: ${orderId}`);
```

## Primary Workflows

### 1. Exception Handling Setup
When adding error tracking to a feature:
1. Identify areas where exceptions are expected
2. Wrap in try-catch with `Sentry.captureException(error)`
3. Add meaningful context to the error if needed

### 2. Performance Tracing Setup
When instrumenting performance:
1. Identify meaningful actions (button clicks, API calls, function calls)
2. Create spans with descriptive `name` and `op` properties
3. Attach relevant attributes for filtering and analysis
4. Use child spans for nested operations

### 3. Logging Implementation
When adding structured logs:
1. Ensure `enableLogs: true` in Sentry init
2. Use appropriate log level (trace, debug, info, warn, error, fatal)
3. Use `logger.fmt` for template literals with variables
4. Include relevant attributes as second parameter

## References
> **Usage:** Claude should READ these for detailed patterns and configuration.

- `references/sentry-configuration.md` - Sentry initialization and setup patterns
- `references/sentry-tracing.md` - Span instrumentation for components and API calls
- `references/sentry-logging.md` - Structured logging patterns and log levels

## Integration with Error Lifecycle Management
This skill complements `error-lifecycle-management` by providing the instrumentation patterns that feed into error tracking workflows. Use this skill for **implementing** Sentry; use error-lifecycle-management for **responding to** Sentry alerts.
