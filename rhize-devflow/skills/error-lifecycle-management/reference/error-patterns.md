# Common Error Patterns & Solutions

## Next.js Specific Errors

### Hydration Mismatch
**Pattern:** "Text content does not match server-rendered HTML"
**Root Causes:**
1. Date/time rendering without timezone consideration
2. Browser-only APIs used during SSR
3. Conditional rendering based on window object

**Solution Template:**
```typescript
// Safe client-side rendering
const [isClient, setIsClient] = useState(false);
useEffect(() => setIsClient(true), []);

// Or use dynamic import
const ClientOnlyComponent = dynamic(
  () => import('./ClientComponent'),
  { ssr: false }
);
```

### API Route Errors

#### CORS Issues
**Pattern:** "Access to fetch at 'api/...' from origin..."
**Solution:**
```typescript
// api/route.ts
export async function handler(req: NextApiRequest, res: NextApiResponse) {
  // Set CORS headers
  res.setHeader('Access-Control-Allow-Origin', process.env.ALLOWED_ORIGIN);
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE');
  
  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }
}
```

## Supabase Errors

### RLS Policy Violations
**Pattern:** "new row violates row-level security policy"
**Diagnosis Steps:**
1. Check current user context: `supabase.auth.getUser()`
2. Review RLS policies: `scripts/check_rls_policies.sql`
3. Test with service role key (bypasses RLS)

### Connection Pool Exhaustion
**Pattern:** "remaining connection slots are reserved"
**Solution:**
```typescript
// Implement connection pooling
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(url, key, {
  db: {
    pooling_mode: 'transaction',
    max_connections: 10,
    idle_timeout: 20
  }
});
```

## Payload CMS Errors

### GraphQL Query Depth
**Pattern:** "Query depth limit exceeded"
**Solution:** Implement query depth limiting and pagination
```typescript
// Limit depth in Payload config
export default buildConfig({
  graphQL: {
    maxDepth: 5,
    complexity: 1000
  }
});
```

### Memory Leaks in Hooks
**Pattern:** "JavaScript heap out of memory"
**Detection:** Use `scripts/detect_memory_leak.js`
**Common Causes:**
1. Infinite loops in afterRead hooks
2. Large data transformations without cleanup
3. Circular references in collection relationships

## TypeScript Build Errors

### Module Resolution Issues
**Pattern:** "Cannot find module" or "Module not found"
**Solutions:**
```json
// tsconfig.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"],
      "@components/*": ["./src/components/*"]
    }
  }
}
```

### Type Definition Conflicts
**Pattern:** "Duplicate identifier" or "Cannot redeclare"
**Solution:**
```typescript
// Add to tsconfig.json
{
  "compilerOptions": {
    "skipLibCheck": true,
    "typeRoots": ["./node_modules/@types", "./types"]
  }
}
```

## Vercel Deployment Errors

### Build Memory Exceeded
**Pattern:** "Error: The build exceeded the maximum memory"
**Solution:**
```json
// vercel.json
{
  "functions": {
    "pages/api/*.ts": {
      "maxDuration": 30,
      "memory": 3008
    }
  }
}
```

### Environment Variable Issues
**Pattern:** "undefined is not a valid URL"
**Checklist:**
1. Verify all env vars in Vercel dashboard
2. Check for NEXT_PUBLIC_ prefix for client-side vars
3. Rebuild after adding new env vars
4. Use `vercel env pull` to sync locally

---

## VBA LMS Specific Errors

### Payload CMS 3.x Errors

#### Collection Access Denied
**Pattern:** "You are not allowed to perform this action"
**Root Causes:**
1. User role doesn't match access control function
2. Access function checking wrong field (e.g., `user.role` vs `user.roles`)
3. Missing admin override in access config

**Solution:**
```typescript
// Check access control in collection config
access: {
  read: ({ req: { user } }) => {
    if (!user) return false;
    if (user.roles?.includes('admin')) return true;
    return { 'parent.value': { equals: user.id } };
  },
}
```

#### Payload Type Generation Errors
**Pattern:** "Property 'X' does not exist on type 'Y'"
**Causes:** Types out of sync with collection schema
**Solution:**
```bash
cd vba-hoops
yarn generate:types
# Then check rhize-lms/next-frontend for type imports
```

#### Relationship Population Failures
**Pattern:** "Cannot read properties of undefined (reading 'id')"
**Causes:** Relationship not populated or deleted reference
**Solution:**
```typescript
// Always check if relationship is populated
const teamName = typeof player.team === 'object'
  ? player.team?.name
  : 'Unknown Team';
```

### React Query Errors (Frontend)

#### Stale Data After Mutation
**Pattern:** UI doesn't update after successful mutation
**Causes:** Missing query invalidation
**Solution:**
```typescript
const mutation = useMutation({
  mutationFn: updateRegistration,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['registrations'] });
    queryClient.invalidateQueries({ queryKey: ['user-registrations'] });
  },
});
```

#### Infinite Refetch Loop
**Pattern:** Network tab shows endless API calls
**Causes:** Unstable query key or dependency
**Solution:**
```typescript
// Bad: Creates new object reference each render
useQuery({ queryKey: ['teams', { filters }] })

// Good: Stable reference
const stableFilters = useMemo(() => filters, [filters.season, filters.league]);
useQuery({ queryKey: ['teams', stableFilters] })
```

### PostgreSQL/Database Errors

#### Connection Pool Exhaustion
**Pattern:** "too many clients already" or "connection timeout"
**Causes:** Unreleased connections, too many concurrent requests
**Solution:**
```typescript
// In Payload config, ensure proper pool settings
db: postgres({
  pool: {
    min: 2,
    max: 10,
    idleTimeoutMillis: 30000,
  },
}),
```

#### Migration Failures
**Pattern:** "relation already exists" or "column does not exist"
**Solution:**
```bash
cd vba-hoops
yarn payload migrate:status  # Check pending migrations
yarn payload migrate         # Run migrations
# If issues, check migrations/ folder for conflicts
```

### Authorize.net Payment Errors

#### Accept.js Loading Failure
**Pattern:** "Accept is not defined" or Accept.js fails to load
**Causes:** Script blocked, wrong environment URL
**Solution:**
```typescript
// Ensure correct Accept.js URL for environment
const ACCEPT_JS_URL = process.env.NODE_ENV === 'production'
  ? 'https://js.authorize.net/v1/Accept.js'
  : 'https://jstest.authorize.net/v1/Accept.js';
```

#### Payment Token Expiration
**Pattern:** "The OTS token has expired"
**Causes:** Token not used within 15 minutes
**Solution:** Generate token immediately before submission, add retry logic

### Cross-Repository API Errors

#### CORS Between Frontend and Backend
**Pattern:** "Access to fetch at 'admin.vbahoops.com' blocked by CORS"
**Solution:** Check `payload.config.ts` CORS settings:
```typescript
cors: [
  'https://vbahoops.com',
  'http://localhost:3001',  // Frontend dev
],
```

#### JWT Token Issues
**Pattern:** Frontend gets 401 after successful login
**Causes:** Token not properly stored or sent
**Solution:**
```typescript
// Verify token is included in requests
const response = await fetch(`${BACKEND_URL}/api/users/me`, {
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  },
});
```

### Domain-Specific Errors

#### Registration Validation Failures
**Pattern:** "Player already registered for this season"
**Solution:** Check registration hooks in `vba-hoops/src/collections/Registrations.ts`

#### Game Score Submission Errors
**Pattern:** "Cannot update game - not authorized"
**Causes:** User is not the assigned coach or admin
**Solution:** Verify coach assignment and access control logic

#### Parent Portal Access Issues
**Pattern:** "No registrations found" but user has registered players
**Causes:** Parent-player relationship not properly linked
**Solution:** Check Users-Players relationship and access queries
