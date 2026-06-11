# Advanced Sentry Query Patterns

## Error Trend Analysis

### Spike Detection Query
```
is:unresolved 
error.type:[TypeError, ReferenceError] 
timesSeen:>100 
firstSeen:+24h
```

### User Impact Assessment
```
is:unresolved 
user.email:* 
has:user.email 
timesSeen:>10
sorted:user
```

### Error Clustering by Release
```
is:unresolved 
release:*
firstSeen:-7d
sorted:freq
```

## Performance Queries

### Slow API Endpoints
```
transaction.duration:>3s 
transaction.op:http.server
http.status_code:[200, 201]
```

### Database Query Performance
```
transaction.duration:>1s
span.op:db
span.description:"SELECT *"
```

### Frontend Vitals
```
measurements.lcp:>2.5s OR
measurements.fid:>100ms OR
measurements.cls:>0.1
```

### Memory Issues
```
error.type:RangeError
message:"*Maximum call stack*"
OR message:"*heap out of memory*"
```

## Custom Fingerprinting Rules

For better error grouping:
```javascript
// sentry.client.config.ts
import * as Sentry from '@sentry/nextjs';

Sentry.init({
  beforeSend(event, hint) {
    // Group similar hydration errors
    if (event.exception?.values?.[0]?.value?.includes('Hydration')) {
      event.fingerprint = ['hydration-error', event.exception.values[0].type];
    }
    
    // Group by API endpoint
    if (event.transaction?.includes('/api/')) {
      event.fingerprint = ['api-error', event.transaction];
    }
    
    // Group database errors
    if (event.exception?.values?.[0]?.value?.includes('ECONNREFUSED')) {
      event.fingerprint = ['database-connection-error'];
    }
    
    return event;
  }
});
```

## Alert Rules Configuration

### Critical Error Surge
- **Condition:** Error rate increases by 300% in 5 minutes
- **Filter:** `level:error AND !environment:development`
- **Action:** Trigger PagerDuty + Slack
- **Query:** `is:unresolved level:error firstSeen:+5m`

### Performance Degradation
- **Condition:** P95 latency > 3 seconds for 10 minutes
- **Filter:** `transaction.duration:>3s`
- **Action:** Create GitHub issue + notify team

### User Experience Impact
- **Condition:** More than 10 unique users affected in 1 hour
- **Filter:** `has:user.email timesSeen:>10`
- **Action:** Escalate to on-call engineer

## Breadcrumb Analysis Patterns

### Navigation Tracking
```javascript
Sentry.addBreadcrumb({
  message: 'User navigated',
  category: 'navigation',
  level: 'info',
  data: {
    from: previousRoute,
    to: currentRoute
  }
});
```

### API Call Tracking
```javascript
Sentry.addBreadcrumb({
  message: `API call to ${endpoint}`,
  category: 'api',
  level: 'info',
  data: {
    method,
    status: response.status,
    duration: endTime - startTime
  }
});
```

## Advanced Filtering

### By Browser
```
browser.name:["Chrome", "Safari", "Firefox"]
!browser.version:["<90", "<14", "<95"]
```

### By Device Type
```
device.family:["iPhone", "iPad"]
OR device.family:["Samsung", "Pixel"]
```

### By Custom Tags
```
tags.feature:checkout
tags.plan:enterprise
tags.deployment:canary
```

## Dashboard Queries

### Error Rate by Feature
```
GROUP BY tags.feature
AGGREGATE count()
WHERE is:unresolved
```

### Performance by Page
```
GROUP BY transaction
AGGREGATE p95(transaction.duration)
WHERE transaction.op:pageload
```

### User Impact Analysis
```
GROUP BY user.email
AGGREGATE count()
WHERE level:error
SORT BY count DESC
```
