# /rhize-devflow:browser-test

Run visual and form tests using Chrome DevTools MCP.

## Aliases
- `@browser-test`
- `/rhize-devflow:browser-test`

## Usage
```
/rhize-devflow:browser-test [url]
/rhize-devflow:browser-test --responsive http://localhost:3000
/rhize-devflow:browser-test --form "email=test@test.com,password=Test123" http://localhost:3000/login
```

## What This Command Does

### Visual Testing Mode (default)
1. Navigate to target URL
2. Take full-page screenshot
3. Check for console errors
4. Report visual issues

### Responsive Mode (--responsive)
1. Navigate to target URL
2. Take screenshots at multiple viewports:
   - Mobile: 375x667
   - Tablet: 768x1024
   - Desktop: 1440x900
3. Compare layouts
4. Report overflow/layout issues

### Form Testing Mode (--form)
1. Navigate to target URL
2. Fill form with provided data
3. Submit form
4. Verify:
   - No console errors
   - Expected redirect/response
   - Success message displayed

## MCP Tools Used

- `navigate_page` - Load target URL
- `take_screenshot` - Capture visual state
- `resize_page` / `emulate` - Change viewport
- `fill`, `fill_form` - Enter form data
- `click` - Submit forms
- `list_console_messages` - Check for errors
- `wait_for` - Wait for results

## Expected Output

### Visual Test
```
## Visual Test: http://localhost:3000/pricing

**Screenshot captured:** pricing-1702828800.png

**Console Check:** ✅ No errors

**Visual Issues:**
- None detected
```

### Responsive Test
```
## Responsive Test: http://localhost:3000/pricing

**Screenshots:**
- Mobile (375px): pricing-mobile.png
- Tablet (768px): pricing-tablet.png
- Desktop (1440px): pricing-desktop.png

**Layout Issues:**
1. ⚠️ Mobile: Horizontal overflow on pricing table
2. ⚠️ Tablet: Button text truncated in CTA section

**Recommendations:**
- Add overflow-x: auto to pricing table on mobile
- Reduce font-size or use responsive text for CTA buttons
```

### Form Test
```
## Form Test: http://localhost:3000/login

**Form filled:**
- email: test@test.com
- password: ********

**Submit result:** ✅ Success
- Redirected to: /dashboard
- Console errors: None

**Verification:**
- Welcome message displayed ✅
- User avatar loaded ✅
```

## Viewport Presets

| Device | Width | Height | Scale |
|--------|-------|--------|-------|
| iPhone SE | 375 | 667 | 2x |
| iPhone 14 | 390 | 844 | 3x |
| iPad | 768 | 1024 | 2x |
| Desktop | 1440 | 900 | 1x |
| Large Desktop | 1920 | 1080 | 1x |

## Follow-up Actions

After testing:
- Fix layout issues identified
- Re-run `@browser-test --responsive` to verify
- Use `@browser-debug` for any console errors
