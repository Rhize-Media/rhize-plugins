# Chrome DevTools MCP - Examples & Prompts Reference

> Detailed examples, effective prompts, and integration patterns

---

## Effective Prompts by Category

### Performance Analysis

```markdown
# Basic Performance Check
"Check the performance of http://localhost:3000"

# With User Interaction
"Navigate to http://localhost:3000/dashboard, scroll to the bottom, 
then analyze the performance trace for layout shifts"

# Mobile Performance
"Emulate iPhone 14 Pro, navigate to http://localhost:3000, 
and check Core Web Vitals"

# Specific Metrics
"Analyze the Largest Contentful Paint (LCP) for http://localhost:3000/products 
and identify what's causing slow rendering"
```

### Network Debugging

```markdown
# List All Requests
"Navigate to http://localhost:3000/api-test and show me all network requests"

# Filter by Endpoint
"Show all network requests to /api/auth/* on http://localhost:3000/login"

# Debug CORS
"Navigate to http://localhost:3000/external-api and identify any CORS errors"

# API Response Inspection
"Submit the form on http://localhost:3000/contact and show me the 
full request/response for the API call including headers"

# Failed Requests
"Navigate to http://localhost:3000/dashboard and list all failed 
network requests with their error details"

# Auth Flow Debug
"Navigate to http://localhost:3000/login, fill email=test@test.com 
password=test123, submit, and show all network requests during the auth flow"
```

### Console & Error Analysis

```markdown
# All Console Output
"Open http://localhost:3000 and show me all console messages"

# Errors Only
"Navigate to http://localhost:3000/broken-page and list all 
JavaScript errors with full stack traces"

# Warnings Analysis
"Check http://localhost:3000 for any console warnings about 
deprecated features or accessibility issues"

# Runtime Error Investigation
"Navigate to http://localhost:3000/checkout, click the submit button, 
and capture any console errors that occur"
```

### Visual Testing & Screenshots

```markdown
# Full Page Screenshot
"Take a full-page screenshot of http://localhost:3000/pricing"

# Specific Element
"Take a screenshot of the navigation header on http://localhost:3000"

# Multiple Viewports
"Take screenshots of http://localhost:3000 at:
- Desktop: 1440x900
- Tablet: 768x1024
- Mobile: 375x667"

# Before/After States
"Navigate to http://localhost:3000/toggle-demo, take a screenshot, 
click the toggle button, then take another screenshot"
```

### Form Automation

```markdown
# Simple Form Fill
"Navigate to http://localhost:3000/contact, fill:
- name: John Doe
- email: john@example.com
- message: Test message
Then submit the form"

# Login Flow
"Go to http://localhost:3000/login, enter test@example.com as email 
and Password123! as password, then click Sign In"

# Complex Form
"Fill the registration form at http://localhost:3000/register with:
- firstName: Test
- lastName: User
- email: test.user@example.com
- password: SecurePass123!
- confirmPassword: SecurePass123!
Then submit and verify the redirect to /welcome"

# File Upload
"Navigate to http://localhost:3000/upload and upload the file 
/path/to/test-document.pdf"
```

### Navigation & Multi-Tab

```markdown
# Wait for Content
"Navigate to http://localhost:3000/dashboard and wait for 
the loading spinner to disappear"

# Multi-Tab Testing
"Open http://localhost:3000/page1 in a new tab, then open 
http://localhost:3000/page2 in another tab, and list all open pages"

# Deep Link Testing
"Navigate to http://localhost:3000/products/123?ref=test&utm_source=email 
and verify the page loads correctly"
```

### Device Emulation

```markdown
# Specific Device
"Emulate iPhone 14 Pro Max and navigate to http://localhost:3000"

# Custom Viewport
"Set viewport to 1920x1080 with 2x device pixel ratio"

# Responsive Testing
"Test http://localhost:3000/responsive at these breakpoints:
- 320px (small mobile)
- 768px (tablet)
- 1024px (desktop)
- 1440px (large desktop)
And report any layout issues"
```

---

## Integration Patterns

### Pattern: Sentry Error Reproduction

```markdown
WORKFLOW: Reproduce Sentry Error

1. [Sentry MCP] Get error details: URL, user action, stack trace
2. [Chrome DevTools] Navigate to the same URL
3. [Chrome DevTools] Perform the triggering action
4. [Chrome DevTools] Capture console errors
5. Compare stack traces

Example prompt sequence:
"Using Sentry, get the details of the most recent unhandled exception"
"Navigate to [url from sentry] and reproduce by [action from sentry]"
"Show me the console errors and compare with the Sentry stack trace"
```

### Pattern: Vercel Deployment Verification

```markdown
WORKFLOW: Post-Deploy Verification

1. [Vercel MCP] Get latest deployment URL
2. [Chrome DevTools] Navigate to deployment
3. [Chrome DevTools] Run performance trace
4. [Chrome DevTools] Check for console errors
5. [Chrome DevTools] Take screenshots

Example prompt sequence:
"Get the URL of the latest Vercel deployment"
"Navigate to [deployment url], check performance, report errors"
"Take screenshots of homepage, login, and dashboard"
```

### Pattern: Full E2E Test Flow

```markdown
WORKFLOW: End-to-End Feature Test

1. [Chrome DevTools] Start fresh (isolated mode)
2. Navigate to starting point
3. Perform all user actions
4. Capture network requests at each step
5. Verify final state
6. Take screenshots as evidence

Example prompt:
"In isolated mode, test the complete signup flow:
1. Navigate to http://localhost:3000/signup
2. Fill and submit registration form
3. Verify redirect to email verification page
4. Navigate to http://localhost:3000/verify?token=test
5. Verify redirect to dashboard
Capture screenshots and any errors at each step"
```

---

## Next.js Specific Examples

### App Router Testing

```markdown
# Server Component Rendering
"Navigate to http://localhost:3000/products and verify the product list 
renders without client-side JavaScript errors"

# Client Component Interaction
"Navigate to http://localhost:3000/cart, click 'Add Item', 
and verify the cart updates without full page reload"

# Loading States
"Navigate to http://localhost:3000/data-heavy-page and capture 
screenshots of the loading skeleton and final loaded state"

# Error Boundaries
"Navigate to http://localhost:3000/error-test and verify 
the error boundary catches and displays the error"
```

### API Route Testing

```markdown
# API Response
"Navigate to http://localhost:3000/test-page, trigger the API call, 
and show me the response from /api/data"

# POST Request
"Navigate to http://localhost:3000/form, submit the form, 
and show the full POST request to /api/submit including body"
```

---

## Payload CMS Testing Examples

```markdown
# Admin Panel
"Navigate to http://localhost:3000/admin and take a screenshot 
of the dashboard"

# Collection CRUD
"Navigate to http://localhost:3000/admin/collections/posts, 
click 'Create New', fill the form, and save"

# Media Upload
"Navigate to http://localhost:3000/admin/collections/media 
and upload /path/to/test-image.jpg"
```

---

## Supabase Integration Testing

```markdown
# Auth Flow
"Navigate to http://localhost:3000/login, sign in with 
test@example.com, and verify the Supabase session cookie is set"

# Realtime Updates
"Open two tabs to http://localhost:3000/chat, send a message 
in one tab, and verify it appears in the other tab"
```

---

## Debugging Scenarios

### Hydration Mismatch

```markdown
"Navigate to http://localhost:3000/hydration-issue with JavaScript disabled, 
take a screenshot, then enable JavaScript, reload, and compare. 
Also show any hydration-related console errors."
```

### Animation Performance

```markdown
"Navigate to http://localhost:3000/animations, start a performance trace, 
trigger all animations, stop the trace, and identify any frames 
that took longer than 16ms"
```

---

## Advanced Scripting

### Custom Assertions

```markdown
"Navigate to http://localhost:3000/dashboard, then evaluate this script 
to verify the data loaded correctly:

const userCount = document.querySelector('.user-count').textContent;
const isValid = parseInt(userCount) > 0;
return { userCount, isValid };
"
```

### Performance Metrics Extraction

```markdown
"Navigate to http://localhost:3000, wait for load, then evaluate:

const timing = performance.timing;
return {
  ttfb: timing.responseStart - timing.navigationStart,
  domContentLoaded: timing.domContentLoadedEventEnd - timing.navigationStart,
  load: timing.loadEventEnd - timing.navigationStart
};
"
```

### Local Storage Inspection

```markdown
"Navigate to http://localhost:3000/app, then evaluate:

return {
  localStorage: Object.fromEntries(Object.entries(localStorage)),
  sessionStorage: Object.fromEntries(Object.entries(sessionStorage))
};
"
```
