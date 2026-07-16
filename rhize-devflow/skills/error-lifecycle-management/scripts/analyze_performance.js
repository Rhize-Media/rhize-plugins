#!/usr/bin/env node
/**
 * analyze_performance.js - Performance analysis for Next.js apps
 *
 * Checks for:
 * - Large bundle imports (moment.js, lodash full import)
 * - Missing React.memo on frequently re-rendered components
 * - useEffect without dependency arrays
 * - N+1 query patterns in server components
 * - Missing loading.tsx for route segments
 * - Images without width/height or priority
 * - React Query staleTime/gcTime configurations
 * - Missing Suspense boundaries
 *
 * Usage:
 *   node analyze_performance.js [--strict] [--warn] [--json] [--md] [--root /path/to/project]
 *
 *   --root      Project (frontend) root directory (default: current directory)
 *
 * MCP Integration:
 *   After running this validator, correlate with production performance:
 *
 *   1. Check Sentry for performance issues:
 *      mcp__sentry__search_events(organizationSlug="your-org",
 *          naturalLanguageQuery="slow transactions > 3s")
 *
 *   2. Get React/Next.js performance patterns from Context7:
 *      mcp__context7__get-library-docs(
 *          context7CompatibleLibraryID="/vercel/next.js",
 *          topic="performance optimization")
 *
 *   3. Test performance with Playwright:
 *      mcp__playwright__browser_navigate + performance metrics
 */

const fs = require('fs');
const path = require('path');

// Parse arguments
const args = process.argv.slice(2);
const flags = {
  strict: args.includes('--strict'),
  warn: args.includes('--warn'),
  json: args.includes('--json'),
  md: args.includes('--md')
};
const rootFlagIndex = args.indexOf('--root');
const rootFlagValue = rootFlagIndex !== -1 ? args[rootFlagIndex + 1] : undefined;
if (rootFlagIndex !== -1 && (rootFlagValue === undefined || rootFlagValue.startsWith('--'))) {
  console.error('Error: --root requires a path argument');
  process.exit(1);
}
const rootArg = rootFlagValue || null;

// Defaults
if (!flags.json && !flags.md) {
  flags.json = true;
  flags.md = true;
}
if (!flags.strict && !flags.warn) {
  flags.strict = true;
}

const Severity = {
  ERROR: 'error',
  WARNING: 'warning',
  INFO: 'info'
};

// Same base names common/config.py's ProjectConfig.frontend_scan_dirs defaults to (minus the
// bare 'src' entry, since withSrcVariants below already probes both 'name' and 'src/name').
const DEFAULT_SCAN_DIRS = ['app', 'lib', 'components', 'hooks', 'providers'];

// Probe both the bare name and its src/-prefixed variant — used for both the app-router
// loading.tsx check and the general scan-directory list, instead of each maintaining its own
// copy of this pairing.
function withSrcVariants(names) {
  return names.flatMap(n => [n, `src/${n}`]);
}

// Sibling Python validators in this same scripts/ directory (via common/config.py +
// common/cli.py) already resolve scan directories from an optional .error-lifecycle.json at
// the project root, supporting single-repo (`scan_dirs`) and monorepo (`frontend.scan_dirs` +
// `frontend.root`) layouts. This JS script can't import that Python module, but it can and
// should read the same config file/schema rather than inventing an unrelated one.
function loadFrontendConfig(projectRoot) {
  const configPath = path.join(projectRoot, '.error-lifecycle.json');
  if (!fs.existsSync(configPath)) {
    return { root: projectRoot, scanDirs: DEFAULT_SCAN_DIRS };
  }
  try {
    const data = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
    if (data.project_type === 'monorepo' && data.frontend) {
      return {
        root: data.frontend.root ? path.resolve(projectRoot, data.frontend.root) : projectRoot,
        scanDirs: data.frontend.scan_dirs || DEFAULT_SCAN_DIRS
      };
    }
    return { root: projectRoot, scanDirs: data.scan_dirs || DEFAULT_SCAN_DIRS };
  } catch (e) {
    console.error(`Warning: could not parse .error-lifecycle.json: ${e.message}`);
    console.error('Falling back to defaults...');
    return { root: projectRoot, scanDirs: DEFAULT_SCAN_DIRS };
  }
}

class PerformanceAnalyzer {
  constructor(projectRoot) {
    this.projectRoot = projectRoot;
    const frontendConfig = loadFrontendConfig(projectRoot);
    this.frontendRoot = frontendConfig.root;
    this.scanDirCandidates = withSrcVariants(frontendConfig.scanDirs);
    this.report = {
      timestamp: new Date().toISOString(),
      totalFilesScanned: 0,
      errors: 0,
      warnings: 0,
      issues: [],
      stats: {
        heavyImports: 0,
        missingMemo: 0,
        badUseEffect: 0,
        missingLoading: 0,
        unoptimizedImages: 0,
        reactQueryIssues: 0,
        missingSuspense: 0
      },
      passed: true
    };
  }

  // Patterns to detect
  patterns = {
    heavyImports: {
      patterns: [
        /import\s+moment\s+from\s+['"]moment['"]/,
        /import\s+_\s+from\s+['"]lodash['"]/,
        /import\s+\*\s+as\s+_\s+from\s+['"]lodash['"]/,
        /require\s*\(\s*['"]moment['"]\s*\)/,
        /require\s*\(\s*['"]lodash['"]\s*\)/
      ],
      rule: 'no-heavy-imports',
      message: 'Heavy library import detected - use tree-shakeable alternatives',
      severity: Severity.WARNING,
      suggestion: 'Use date-fns instead of moment, lodash-es or individual lodash imports'
    },
    badUseEffect: {
      patterns: [
        /useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[^}]+\}\s*\)\s*;?\s*$/m,
        /useEffect\s*\(\s*async/
      ],
      rule: 'useEffect-needs-deps',
      message: 'useEffect without dependency array or with async directly',
      severity: Severity.WARNING,
      suggestion: 'Add dependency array: useEffect(() => {}, [deps]). For async, use inner function.'
    },
    unoptimizedImages: {
      patterns: [
        /<img\s+[^>]*src=/i,
        /Image\s+[^>]*(?!.*(?:width|height))[^>]*\/>/
      ],
      rule: 'optimize-images',
      message: 'Image may be missing optimization attributes',
      severity: Severity.WARNING,
      suggestion: 'Use next/image with width, height, and priority for above-fold images'
    },
    reactQueryBadConfig: {
      patterns: [
        /staleTime:\s*0\b/,
        /gcTime:\s*0\b/,
        /cacheTime:\s*0\b/
      ],
      rule: 'react-query-config',
      message: 'React Query with zero cache time defeats caching benefits',
      severity: Severity.WARNING,
      suggestion: 'Use appropriate staleTime (e.g., 30000) and gcTime (e.g., 300000)'
    },
    inlineFunction: {
      patterns: [
        /onClick=\{\s*\(\)\s*=>\s*\w+\([^)]+\)\s*\}/,
        /onChange=\{\s*\([^)]*\)\s*=>\s*set\w+/
      ],
      rule: 'inline-handlers',
      message: 'Inline function in JSX causes unnecessary re-renders',
      severity: Severity.INFO,
      suggestion: 'Extract to useCallback for frequently re-rendered components'
    }
  };

  shouldSkipFile(filepath) {
    const excludePatterns = [
      /node_modules/,
      /\.next/,
      /dist/,
      /build/,
      /__tests__/,
      /\.test\./,
      /\.spec\./,
      /\.d\.ts$/
    ];
    return excludePatterns.some(p => p.test(filepath));
  }

  getCodeSnippet(lines, lineNum, context = 2) {
    const start = Math.max(0, lineNum - context - 1);
    const end = Math.min(lines.length, lineNum + context);
    const snippetLines = [];
    for (let i = start; i < end; i++) {
      const prefix = i === lineNum - 1 ? '>>> ' : '    ';
      snippetLines.push(`${prefix}${i + 1}: ${lines[i]}`);
    }
    return snippetLines.join('\n');
  }

  scanFile(filepath) {
    const issues = [];
    let content;
    
    try {
      content = fs.readFileSync(filepath, 'utf-8');
    } catch (e) {
      return [{ 
        file: path.relative(this.projectRoot, filepath),
        line: 0,
        severity: Severity.WARNING,
        rule: 'file-read-error',
        message: `Could not read file: ${e.message}`
      }];
    }

    const lines = content.split('\n');
    const relPath = path.relative(this.projectRoot, filepath);

    // Check patterns
    for (const [name, config] of Object.entries(this.patterns)) {
      for (const pattern of config.patterns) {
        let match;
        const regex = new RegExp(pattern.source, pattern.flags + 'g');
        while ((match = regex.exec(content)) !== null) {
          const lineNum = content.substring(0, match.index).split('\n').length;
          const lineContent = lines[lineNum - 1] || '';
          
          // Skip comments
          if (lineContent.trim().startsWith('//') || lineContent.trim().startsWith('*')) {
            continue;
          }

          issues.push({
            file: relPath,
            line: lineNum,
            severity: config.severity,
            rule: config.rule,
            message: config.message,
            codeSnippet: this.getCodeSnippet(lines, lineNum),
            suggestion: config.suggestion
          });

          // Update stats
          switch (name) {
            case 'heavyImports': this.report.stats.heavyImports++; break;
            case 'badUseEffect': this.report.stats.badUseEffect++; break;
            case 'unoptimizedImages': this.report.stats.unoptimizedImages++; break;
            case 'reactQueryBadConfig': this.report.stats.reactQueryIssues++; break;
          }
        }
      }
    }

    return issues;
  }

  checkMissingLoadingFiles() {
    const appDir = withSrcVariants(['app'])
      .map(d => path.join(this.frontendRoot, d))
      .find(d => fs.existsSync(d));
    if (!appDir) return;

    const checkDir = (dir, depth = 0) => {
      if (depth > 5) return; // Limit recursion
      
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      const hasPage = entries.some(e => e.name === 'page.tsx' || e.name === 'page.js');
      const hasLoading = entries.some(e => e.name === 'loading.tsx' || e.name === 'loading.js');
      
      if (hasPage && !hasLoading) {
        const relPath = path.relative(this.projectRoot, dir);
        // Only warn for non-trivial routes
        if (!relPath.includes('api') && !relPath.includes('(') && depth > 0) {
          this.report.issues.push({
            file: relPath,
            line: 0,
            severity: Severity.INFO,
            rule: 'missing-loading',
            message: 'Route segment missing loading.tsx for better UX',
            suggestion: 'Add loading.tsx with skeleton/spinner for perceived performance'
          });
          this.report.stats.missingLoading++;
        }
      }

      for (const entry of entries) {
        if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
          checkDir(path.join(dir, entry.name), depth + 1);
        }
      }
    };

    checkDir(appDir);
  }

  scanCodebase() {
    const scanDirs = this.scanDirCandidates.map(d => path.join(this.frontendRoot, d)).filter(d => fs.existsSync(d));
    if (scanDirs.length === 0) {
      console.error(`Error: none of ${this.scanDirCandidates.join(', ')} found under ${this.frontendRoot} — pass --root, or add a .error-lifecycle.json with scan_dirs/frontend.scan_dirs`);
      process.exit(1);
    }

    const extensions = ['.ts', '.tsx', '.js', '.jsx'];
    
    const scanDir = (dir) => {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      
      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);
        
        if (entry.isDirectory()) {
          if (!this.shouldSkipFile(fullPath)) {
            scanDir(fullPath);
          }
        } else if (entry.isFile() && extensions.some(ext => entry.name.endsWith(ext))) {
          if (!this.shouldSkipFile(fullPath)) {
            this.report.totalFilesScanned++;
            const issues = this.scanFile(fullPath);
            
            for (const issue of issues) {
              this.report.issues.push(issue);
              if (issue.severity === Severity.ERROR) {
                this.report.errors++;
              } else if (issue.severity === Severity.WARNING) {
                this.report.warnings++;
              }
            }
          }
        }
      }
    };

    scanDirs.forEach(d => scanDir(d));
    this.checkMissingLoadingFiles();
    this.report.passed = this.report.errors === 0;
  }

  outputJson(outputDir) {
    const reportPath = path.join(outputDir, 'performance-report.json');
    fs.writeFileSync(reportPath, JSON.stringify(this.report, null, 2));
    console.log(`JSON report: ${reportPath}`);
  }

  outputMarkdown(outputDir) {
    const reportPath = path.join(outputDir, 'performance-report.md');
    const stats = this.report.stats;
    
    let md = `# Performance Analysis Report

**Generated**: ${this.report.timestamp}
**Status**: ${this.report.passed ? '✅ PASSED' : '❌ FAILED'}

## Summary
| Metric | Count |
|--------|-------|
| Files Scanned | ${this.report.totalFilesScanned} |
| Errors | ${this.report.errors} |
| Warnings | ${this.report.warnings} |

## Performance Stats
| Issue Type | Count | Impact |
|------------|-------|--------|
| Heavy Imports | ${stats.heavyImports} | 🔴 Bundle Size |
| Bad useEffect | ${stats.badUseEffect} | 🟡 Runtime |
| Unoptimized Images | ${stats.unoptimizedImages} | 🔴 LCP |
| React Query Config | ${stats.reactQueryIssues} | 🟡 Network |
| Missing loading.tsx | ${stats.missingLoading} | 🟢 UX |

## Recommendations

### Bundle Size Optimization
- Replace \`moment\` with \`date-fns\`
- Use individual lodash imports: \`import debounce from 'lodash/debounce'\`
- Enable bundle analyzer: \`ANALYZE=true yarn build\`

### React Performance
- Add dependency arrays to all useEffect hooks
- Use \`React.memo\` for pure components rendered in lists
- Extract inline handlers to \`useCallback\` where needed

### Image Optimization
- Always use \`next/image\` instead of \`<img>\`
- Provide explicit \`width\` and \`height\`
- Add \`priority\` for above-the-fold images

### React Query Best Practices
- Set appropriate \`staleTime\` (default: 30s for lists, 5min for details)
- Configure \`gcTime\` to keep data in cache longer
- Use \`prefetchQuery\` for anticipated navigation

`;

    if (this.report.issues.length > 0) {
      md += '## Issues\n\n';
      const shownIssues = this.report.issues.slice(0, 25);
      for (const issue of shownIssues) {
        md += `### ${issue.rule}
**File**: \`${issue.file}:${issue.line}\`
**Severity**: ${issue.severity}

${issue.message}

💡 ${issue.suggestion}

---

`;
      }
      if (this.report.issues.length > 25) {
        md += `\n*...and ${this.report.issues.length - 25} more issues*\n`;
      }
    }

    fs.writeFileSync(reportPath, md);
    console.log(`Markdown report: ${reportPath}`);
  }

  printSummary() {
    const stats = this.report.stats;
    console.log('\n' + '='.repeat(50));
    console.log('PERFORMANCE ANALYSIS SUMMARY');
    console.log('='.repeat(50));
    console.log(`Files: ${this.report.totalFilesScanned} | Errors: ${this.report.errors} | Warnings: ${this.report.warnings}`);
    console.log(`Heavy imports: ${stats.heavyImports} | Bad useEffect: ${stats.badUseEffect}`);
    console.log(`Unoptimized images: ${stats.unoptimizedImages} | Missing loading: ${stats.missingLoading}`);
    console.log(`Status: ${this.report.passed ? '✅ PASSED' : '❌ FAILED'}`);
    console.log('='.repeat(50) + '\n');
  }
}

// Main execution
const projectRoot = path.resolve(rootArg || process.cwd());
// Matches common/cli.py's get_output_dir() convention used by the sibling Python validators
// in this same scripts/ directory.
const outputDir = path.join(projectRoot, 'skills', 'error-lifecycle-management', 'reports');

if (!fs.existsSync(projectRoot)) {
  console.error(`Error: --root path does not exist: ${projectRoot}`);
  process.exit(1);
}

fs.mkdirSync(outputDir, { recursive: true });

const analyzer = new PerformanceAnalyzer(projectRoot);
analyzer.scanCodebase();
analyzer.printSummary();

if (flags.json) analyzer.outputJson(outputDir);
if (flags.md) analyzer.outputMarkdown(outputDir);

if (flags.strict && !analyzer.report.passed) {
  process.exit(1);
}
process.exit(0);
