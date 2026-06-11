# Sentry Tracing & Spans

## Overview

Spans should be created for meaningful actions within an application:
- Button clicks and user interactions
- API calls and network requests
- Function calls and computations
- Child spans can exist within parent spans for nested operations

## Custom Span Instrumentation

Use `Sentry.startSpan` to create spans with meaningful `name` and `op` properties.

### Component Actions (UI Interactions)

```typescript
import * as Sentry from "@sentry/nextjs";

function TestComponent() {
  const handleTestButtonClick = () => {
    // Create a span to measure performance
    Sentry.startSpan(
      {
        op: "ui.click",
        name: "Test Button Click",
      },
      (span) => {
        const value = "some config";
        const metric = "some metric";

        // Add attributes for filtering and analysis
        span.setAttribute("config", value);
        span.setAttribute("metric", metric);

        doSomething();
      },
    );
  };

  return (
    <button type="button" onClick={handleTestButtonClick}>
      Test Sentry
    </button>
  );
}
```

### API Calls (HTTP Client)

```typescript
import * as Sentry from "@sentry/nextjs";

async function fetchUserData(userId: string) {
  return Sentry.startSpan(
    {
      op: "http.client",
      name: `GET /api/users/${userId}`,
    },
    async (span) => {
      const response = await fetch(`/api/users/${userId}`);

      // Add response metadata
      span.setAttribute("http.status_code", response.status);

      const data = await response.json();
      return data;
    },
  );
}
```

### Async Operations with Return Values

```typescript
async function processOrder(orderId: string) {
  return Sentry.startSpan(
    {
      op: "function",
      name: "Process Order",
    },
    async (span) => {
      span.setAttribute("orderId", orderId);

      const result = await orderService.process(orderId);

      span.setAttribute("itemCount", result.items.length);
      span.setAttribute("total", result.total);

      return result;
    },
  );
}
```

## Common Operation Types (`op`)

| Operation | Use Case |
|-----------|----------|
| `ui.click` | Button clicks, link clicks |
| `ui.action` | Generic UI interactions |
| `http.client` | Outbound HTTP requests |
| `http.server` | Incoming HTTP requests |
| `db.query` | Database queries |
| `function` | Generic function execution |
| `task` | Background tasks |
| `queue.process` | Queue processing |

## Best Practices

1. **Meaningful Names**: Use descriptive names that identify the action
   - Good: `"Submit Registration Form"`, `"GET /api/users/:id"`
   - Bad: `"click"`, `"fetch"`

2. **Relevant Attributes**: Attach data useful for debugging and filtering
   - User IDs, entity IDs, counts, status codes
   - Avoid sensitive data (passwords, tokens, PII)

3. **Consistent Operations**: Use standard `op` values for similar actions
   - All API calls should use `http.client`
   - All button clicks should use `ui.click`

4. **Child Spans**: Nest spans for complex operations
   ```typescript
   Sentry.startSpan({ op: "checkout", name: "Checkout Flow" }, async () => {
     await Sentry.startSpan({ op: "function", name: "Validate Cart" }, validateCart);
     await Sentry.startSpan({ op: "http.client", name: "Process Payment" }, processPayment);
     await Sentry.startSpan({ op: "function", name: "Create Order" }, createOrder);
   });
   ```
