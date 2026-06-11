# Performance Optimization Guide

## Bundle Size Analysis

### Quick Wins

#### 1. Dynamic Imports for Heavy Components
```typescript
const HeavyChart = dynamic(() => import('./HeavyChart'), {
  loading: () => <Skeleton />,
  ssr: false
});
```

#### 2. Tree Shaking Lodash/Moment
```typescript
// Bad
import _ from 'lodash';
import moment from 'moment';

// Good
import debounce from 'lodash/debounce';
import dayjs from 'dayjs'; // Smaller alternative
```

#### 3. Image Optimization
```typescript
import Image from 'next/image';

// Automatic optimization
<Image 
  src="/hero.jpg"
  width={1200}
  height={600}
  priority // For above-fold images
  placeholder="blur"
  blurDataURL={dataUrl}
/>
```

### Bundle Analysis Commands
```bash
# Analyze bundle composition
ANALYZE=true npm run build

# Check bundle size
npm run build -- --stats

# Find large dependencies
npm list --depth=0 | grep -E "[0-9]+\.[0-9]+MB"
```

## Database Query Optimization

### N+1 Query Detection
```typescript
// Bad - N+1 queries
const teams = await getTeams();
for (const team of teams) {
  team.players = await getPlayersByTeamId(team.id);
}

// Good - Single query with join
const teamsWithPlayers = await supabase
  .from('teams')
  .select(`
    *,
    players (*)
  `);
```

### Indexing Strategy
```sql
-- For Supabase/PostgreSQL
-- Analyze slow queries
EXPLAIN ANALYZE 
SELECT * FROM matches 
WHERE league_id = $1 AND status = 'active';

-- Create appropriate index
CREATE INDEX idx_matches_league_status 
ON matches(league_id, status) 
WHERE deleted_at IS NULL;

-- Partial index for common queries
CREATE INDEX idx_active_matches 
ON matches(league_id) 
WHERE status = 'active' AND deleted_at IS NULL;
```

### Query Batching with DataLoader
```typescript
import DataLoader from 'dataloader';

const userLoader = new DataLoader(async (userIds) => {
  const users = await supabase
    .from('users')
    .select('*')
    .in('id', userIds);
  
  // Map back to original order
  return userIds.map(id => 
    users.data.find(user => user.id === id)
  );
});

// Usage
const user = await userLoader.load(userId);
```

## React Performance

### Memo Usage Patterns
```typescript
// Expensive list items
const TeamCard = memo(({ team }) => {
  return <div>...</div>;
}, (prevProps, nextProps) => {
  // Custom comparison
  return prevProps.team.id === nextProps.team.id &&
         prevProps.team.updatedAt === nextProps.team.updatedAt;
});

// Expensive computations
const statistics = useMemo(() => {
  return calculateComplexStats(matches);
}, [matches]);

// Stable callbacks
const handleClick = useCallback((id) => {
  // Handle click
}, [dependency]);
```

### Virtual Scrolling for Large Lists
```typescript
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={teams.length}
  itemSize={80}
  width="100%"
>
  {({ index, style }) => (
    <div style={style}>
      <TeamRow team={teams[index]} />
    </div>
  )}
</FixedSizeList>
```

### Suspense and Lazy Loading
```typescript
const LazyComponent = lazy(() => import('./HeavyComponent'));

function App() {
  return (
    <Suspense fallback={<Loading />}>
      <LazyComponent />
    </Suspense>
  );
}
```

## API Performance

### Response Caching
```typescript
// API route with caching
export async function GET(request: Request) {
  return NextResponse.json(data, {
    headers: {
      'Cache-Control': 'public, s-maxage=10, stale-while-revalidate=59',
    },
  });
}
```

### Pagination Implementation
```typescript
// Cursor-based pagination
const PAGE_SIZE = 20;

export async function getMatches(cursor?: string) {
  let query = supabase
    .from('matches')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(PAGE_SIZE);
    
  if (cursor) {
    query = query.lt('created_at', cursor);
  }
  
  const { data } = await query;
  
  return {
    data,
    nextCursor: data?.[data.length - 1]?.created_at
  };
}
```

## Monitoring & Metrics

### Web Vitals Tracking
```typescript
// pages/_app.tsx or app/layout.tsx
export function reportWebVitals(metric) {
  const body = JSON.stringify(metric);
  const url = '/api/analytics';
  
  // Use sendBeacon if available
  if (navigator.sendBeacon) {
    navigator.sendBeacon(url, body);
  } else {
    fetch(url, { body, method: 'POST' });
  }
}
```

### Custom Performance Marks
```typescript
// Mark important timings
performance.mark('data-fetch-start');
const data = await fetchData();
performance.mark('data-fetch-end');

// Measure duration
performance.measure(
  'data-fetch',
  'data-fetch-start',
  'data-fetch-end'
);

// Get measurement
const measure = performance.getEntriesByName('data-fetch')[0];
console.log(`Data fetch took ${measure.duration}ms`);
```

## Deployment Optimizations

### Vercel Configuration
```json
// vercel.json
{
  "functions": {
    "pages/api/heavy-endpoint.ts": {
      "maxDuration": 60,
      "memory": 3008
    }
  },
  "regions": ["iad1", "sfo1"],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {
          "key": "X-Content-Type-Options",
          "value": "nosniff"
        }
      ]
    }
  ]
}
```

### Edge Runtime for Fast APIs
```typescript
// app/api/fast/route.ts
export const runtime = 'edge';

export async function GET() {
  return Response.json({ fast: true });
}
```
