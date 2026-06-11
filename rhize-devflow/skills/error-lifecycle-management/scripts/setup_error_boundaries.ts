#!/usr/bin/env node
/**
 * Automatically adds error boundaries to React components in a Next.js project.
 * Creates error.tsx files and wraps components with error boundary HOCs.
 */

import * as fs from 'fs';
import * as path from 'path';

const ERROR_BOUNDARY_TEMPLATE = `'use client';

import { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log the error to Sentry
    Sentry.captureException(error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-4">
      <div className="mx-auto max-w-md text-center">
        <h2 className="mb-4 text-2xl font-bold text-red-600">
          Something went wrong!
        </h2>
        <p className="mb-4 text-gray-600">
          {error.message || 'An unexpected error occurred.'}
        </p>
        {error.digest && (
          <p className="mb-4 text-sm text-gray-500">
            Error ID: {error.digest}
          </p>
        )}
        <button
          onClick={reset}
          className="rounded-md bg-blue-500 px-4 py-2 text-white hover:bg-blue-600"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
`;

const GLOBAL_ERROR_TEMPLATE = `'use client';

import * as Sentry from '@sentry/nextjs';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  Sentry.captureException(error);

  return (
    <html>
      <body>
        <div className="flex min-h-screen flex-col items-center justify-center">
          <h2 className="mb-4 text-2xl font-bold">Critical Error</h2>
          <p className="mb-4">The application encountered a critical error.</p>
          <button onClick={reset}>Reload Application</button>
        </div>
      </body>
    </html>
  );
}
`;

const ERROR_BOUNDARY_HOC = `import React, { Component, ErrorInfo, ReactNode } from 'react';
import * as Sentry from '@sentry/nextjs';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
    Sentry.withScope((scope) => {
      scope.setContext('errorBoundary', {
        componentStack: errorInfo.componentStack,
      });
      Sentry.captureException(error);
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="error-boundary-fallback">
            <h2>Oops! Something went wrong.</h2>
            <details style={{ whiteSpace: 'pre-wrap' }}>
              {this.state.error?.toString()}
            </details>
          </div>
        )
      );
    }

    return this.props.children;
  }
}

export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallback?: ReactNode
) {
  return (props: P) => (
    <ErrorBoundary fallback={fallback}>
      <Component {...props} />
    </ErrorBoundary>
  );
}
`;

class ErrorBoundarySetup {
  private projectRoot: string;
  private appDir: string;
  private componentsDir: string;

  constructor(projectRoot: string = process.cwd()) {
    this.projectRoot = projectRoot;
    this.appDir = path.join(projectRoot, 'app');
    this.componentsDir = path.join(projectRoot, 'components');
  }

  /**
   * Add error.tsx files to app directory routes
   */
  async addErrorFiles(): Promise<void> {
    console.log('🔧 Adding error.tsx files to app routes...');
    
    // Add global-error.tsx to root app directory
    const globalErrorPath = path.join(this.appDir, 'global-error.tsx');
    if (!fs.existsSync(globalErrorPath)) {
      fs.writeFileSync(globalErrorPath, GLOBAL_ERROR_TEMPLATE);
      console.log('✅ Created app/global-error.tsx');
    }

    // Walk through app directory and add error.tsx to each route
    this.walkDirectory(this.appDir, (dir) => {
      // Check if this is a route directory (has page.tsx or layout.tsx)
      const hasPage = fs.existsSync(path.join(dir, 'page.tsx'));
      const hasLayout = fs.existsSync(path.join(dir, 'layout.tsx'));
      
      if (hasPage || hasLayout) {
        const errorPath = path.join(dir, 'error.tsx');
        if (!fs.existsSync(errorPath)) {
          fs.writeFileSync(errorPath, ERROR_BOUNDARY_TEMPLATE);
          console.log(`✅ Created ${path.relative(this.projectRoot, errorPath)}`);
        }
      }
    });
  }

  /**
   * Create ErrorBoundary component
   */
  async createErrorBoundaryComponent(): Promise<void> {
    console.log('🔧 Creating ErrorBoundary component...');
    
    if (!fs.existsSync(this.componentsDir)) {
      fs.mkdirSync(this.componentsDir, { recursive: true });
    }

    const errorBoundaryPath = path.join(this.componentsDir, 'ErrorBoundary.tsx');
    if (!fs.existsSync(errorBoundaryPath)) {
      fs.writeFileSync(errorBoundaryPath, ERROR_BOUNDARY_HOC);
      console.log('✅ Created components/ErrorBoundary.tsx');
    }
  }

  /**
   * Update components to use error boundaries
   */
  async wrapComponents(): Promise<void> {
    console.log('🔧 Analyzing components for error boundary wrapping...');
    
    const suggestions: string[] = [];
    
    // Check critical components that should have error boundaries
    const criticalPatterns = [
      'DataTable',
      'Chart',
      'Form',
      'Dashboard',
      'Analytics'
    ];

    this.walkDirectory(this.componentsDir, (dir) => {
      const files = fs.readdirSync(dir);
      
      files.forEach(file => {
        if (file.endsWith('.tsx') || file.endsWith('.jsx')) {
          const filePath = path.join(dir, file);
          const content = fs.readFileSync(filePath, 'utf8');
          
          // Check if it's a critical component
          const isCritical = criticalPatterns.some(pattern => 
            file.includes(pattern) || content.includes(pattern)
          );
          
          // Check if already has error boundary
          const hasErrorBoundary = content.includes('ErrorBoundary') || 
                                   content.includes('withErrorBoundary');
          
          if (isCritical && !hasErrorBoundary) {
            suggestions.push(path.relative(this.projectRoot, filePath));
          }
        }
      });
    });

    if (suggestions.length > 0) {
      console.log('\n📝 Components that should have error boundaries:');
      suggestions.forEach(file => {
        console.log(`   - ${file}`);
      });
      console.log('\n💡 To wrap a component, import and use:');
      console.log(`   import { withErrorBoundary } from '@/components/ErrorBoundary';`);
      console.log(`   export default withErrorBoundary(YourComponent);`);
    }
  }

  /**
   * Walk directory recursively
   */
  private walkDirectory(dir: string, callback: (dir: string) => void): void {
    if (!fs.existsSync(dir)) return;
    
    callback(dir);
    
    const files = fs.readdirSync(dir, { withFileTypes: true });
    files.forEach(file => {
      if (file.isDirectory() && !file.name.includes('node_modules')) {
        this.walkDirectory(path.join(dir, file.name), callback);
      }
    });
  }

  /**
   * Verify Sentry configuration
   */
  async verifySentryConfig(): Promise<boolean> {
    console.log('🔍 Verifying Sentry configuration...');
    
    const sentryFiles = [
      'sentry.client.config.ts',
      'sentry.server.config.ts',
      'sentry.edge.config.ts'
    ];
    
    const missingFiles: string[] = [];
    
    sentryFiles.forEach(file => {
      const filePath = path.join(this.projectRoot, file);
      if (!fs.existsSync(filePath)) {
        missingFiles.push(file);
      }
    });
    
    if (missingFiles.length > 0) {
      console.log('⚠️  Missing Sentry configuration files:');
      missingFiles.forEach(file => console.log(`   - ${file}`));
      console.log('\n💡 Run: npx @sentry/wizard@latest -i nextjs');
      return false;
    }
    
    console.log('✅ Sentry configuration verified');
    return true;
  }

  /**
   * Main setup function
   */
  async setup(): Promise<void> {
    console.log('🚀 Setting up error boundaries for Next.js project\n');

    // Verify project structure
    if (!fs.existsSync(this.appDir)) {
      console.error('❌ No app directory found. This script requires Next.js 13+ with App Router.');
      process.exit(1);
    }

    // Check Sentry configuration
    await this.verifySentryConfig();

    // Add error files
    await this.addErrorFiles();

    // Create ErrorBoundary component
    await this.createErrorBoundaryComponent();

    // Analyze components
    await this.wrapComponents();

    console.log('\n✨ Error boundary setup complete!');
    console.log('\n📚 Next steps:');
    console.log('1. Review the generated error.tsx files');
    console.log('2. Wrap critical components with ErrorBoundary');
    console.log('3. Customize error UI to match your design');
    console.log('4. Test error handling in development');
  }
}

// Run setup if called directly
if (require.main === module) {
  const setup = new ErrorBoundarySetup();
  setup.setup().catch(console.error);
}

export { ErrorBoundarySetup };
