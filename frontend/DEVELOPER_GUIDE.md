# Scout Frontend Developer Guide

A comprehensive guide for developers working with the Scout frontend codebase.

## Getting Started

### First Time Setup

```bash
# 1. Navigate to project
cd frontend

# 2. Install dependencies
npm install

# 3. Copy environment template
cp .env.example .env

# 4. Edit .env with your AWS credentials
nano .env

# 5. Start development server
npm run dev

# 6. Open browser
open http://localhost:5173
```

### Project Structure Overview

```
frontend/
├── public/              # Static assets (favicon)
├── src/
│   ├── components/      # Reusable UI components (8 files)
│   ├── pages/          # Full page components (2 files)
│   ├── hooks/          # Custom React hooks (1 file)
│   ├── services/       # API client layer (1 file)
│   ├── types/          # TypeScript definitions (1 file)
│   ├── App.tsx         # Root app component
│   ├── main.tsx        # React entry point
│   ├── index.css       # Global styles
│   └── amplifyconfiguration.ts  # Cognito config
├── index.html          # HTML template
├── vite.config.ts      # Build configuration
├── tsconfig.json       # TypeScript config
├── tailwind.config.js  # Tailwind theme
├── package.json        # Dependencies
└── documentation/
    ├── README.md           # Full documentation
    ├── QUICK_START.md      # 5-minute setup
    ├── API.md              # API integration guide
    ├── DEPLOYMENT.md       # Deployment procedures
    └── FILES_CREATED.md    # File inventory
```

## Code Organization Principles

### Components

Components live in `src/components/` and follow these rules:

1. **One component per file** (unless very closely related)
2. **Named exports** for components
3. **Props interface** defined above component
4. **Styles via Tailwind** (no separate CSS files)
5. **Self-contained** (no shared state outside hooks)

Example structure:

```typescript
// src/components/MyComponent.tsx
import { SomeIcon } from 'lucide-react';

interface MyComponentProps {
  title: string;
  onAction?: () => void;
}

export function MyComponent({ title, onAction }: MyComponentProps) {
  return (
    <div className="p-4 bg-white rounded-lg">
      <h2 className="text-lg font-bold">{title}</h2>
      {onAction && (
        <button 
          onClick={onAction}
          className="mt-4 px-4 py-2 bg-primary text-white rounded-lg"
        >
          Action
        </button>
      )}
    </div>
  );
}
```

### Pages

Pages are full-screen components that live in `src/pages/` and contain:

1. **Layout logic** (top-level structure)
2. **Data fetching** (via custom hooks)
3. **State management** (filters, pagination, etc.)
4. **Component composition** (multiple smaller components)

Example:

```typescript
// src/pages/MyPage.tsx
import { useState } from 'react';
import { useCustomData } from '@/hooks/useCustom';
import { MyComponent } from '@/components/MyComponent';

export function MyPage() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useCustomData(page);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-8">My Page</h1>
      {isLoading ? <Loading /> : <MyComponent data={data} />}
    </div>
  );
}
```

### Hooks

Custom hooks live in `src/hooks/` and wrap React Query logic:

```typescript
// src/hooks/useCustom.ts
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';

export function useCustomData(page: number) {
  return useQuery({
    queryKey: ['customData', page],
    queryFn: () => api.getCustomData(page),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
```

### Services

The API layer lives in `src/services/api.ts` and contains:

1. **Authenticated fetch wrapper** (adds tokens)
2. **Typed API methods** (getJobs, updateStatus, etc.)
3. **Error handling** (throws on non-2xx)
4. **Type safety** (returns typed promises)

```typescript
// Use in hooks/components:
const data = await api.getJobs(filters);
```

### Types

All TypeScript interfaces live in `src/types/index.ts`:

```typescript
export interface Job {
  jobId: string;
  // ... fields
}

export type ApplicationStatus = 'NOT_APPLIED' | 'APPLIED' | /* ... */;
```

**Always import types**: `import { Job } from '@/types';`

## Development Workflow

### Adding a New Feature

1. **Create types** in `src/types/index.ts` if needed
2. **Create components** in `src/components/` for UI
3. **Create hooks** in `src/hooks/` for data fetching
4. **Wire into pages** in `src/pages/`
5. **Test locally** with `npm run dev`
6. **Run linter**: `npm run lint`
7. **Format code**: `npx prettier --write src/`

### Adding a New API Endpoint

1. **Add method to `api` object** in `src/services/api.ts`

```typescript
export const api = {
  // ... existing methods
  
  getNewData: () => authFetch('/new-endpoint'),
};
```

2. **Create React Query hook** in `src/hooks/useJobs.ts`

```typescript
export function useNewData() {
  return useQuery({
    queryKey: ['newData'],
    queryFn: () => api.getNewData(),
    staleTime: 5 * 60 * 1000,
  });
}
```

3. **Use in component**

```typescript
const { data, isLoading, error } = useNewData();
```

### Styling Guidelines

**Use Tailwind utility classes exclusively**:

```typescript
// Good
<div className="flex items-center gap-4 px-4 py-2 bg-blue-500 text-white rounded-lg">

// Bad (don't use separate CSS)
<div className="my-custom-button">
```

**Common patterns**:

```typescript
// Flexbox layout
<div className="flex items-center justify-between gap-4">

// Grid layout
<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">

// Responsive text
<p className="text-sm sm:text-base lg:text-lg">

// Buttons
<button className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-700 transition-colors">

// Cards
<div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm hover:shadow-md transition-shadow">

// Colors by status
bg-gray-100, bg-blue-100, bg-green-100, bg-red-100, etc.
text-gray-700, text-blue-700, text-green-700, text-red-700, etc.
```

**Responsive breakpoints** (Tailwind defaults):
- `sm`: 640px
- `md`: 768px (main breakpoint for mobile menu)
- `lg`: 1024px
- `xl`: 1280px

### Typescript Best Practices

1. **No implicit any**: Strict mode requires explicit types
2. **Import types**: `import type { Job } from '@/types';`
3. **Define props interfaces**: Always create a `Props` interface
4. **Use union types**: `status: 'active' | 'inactive'`
5. **Avoid `as`**: Let TypeScript infer types

Good example:

```typescript
interface CardProps {
  title: string;
  items: Job[];
  onSelect: (job: Job) => void;
}

export function Card({ title, items, onSelect }: CardProps) {
  // TypeScript knows items is Job[], onSelect gets Job
}
```

## React Query Patterns

### Query Example

```typescript
function MyComponent() {
  const { data, isLoading, error } = useJobs(filters);

  if (isLoading) return <Skeleton />;
  if (error) return <ErrorMessage error={error} />;
  
  return <JobList jobs={data.items} />;
}
```

### Mutation Example

```typescript
function StatusUpdater() {
  const updateStatus = useUpdateStatus();

  const handleUpdate = () => {
    updateStatus.mutate(
      { jobId: '123', status: 'APPLIED' },
      {
        onSuccess: () => {
          // Query automatically invalidated
          // Show success message
        },
        onError: (error) => {
          // Show error message
        },
      }
    );
  };

  return (
    <button 
      onClick={handleUpdate}
      disabled={updateStatus.isPending}
    >
      {updateStatus.isPending ? 'Saving...' : 'Save'}
    </button>
  );
}
```

## Authentication Flow

The Amplify `<Authenticator>` wrapper handles:

1. **Login screen** - Email + password
2. **Signup form** - Create new account
3. **Email verification** - Confirm email
4. **MFA setup** - TOTP enrollment (if required)
5. **Auto-refresh tokens** - Handles expiry

Access current user:

```typescript
import { useAuthenticator } from '@aws-amplify/ui-react';

function MyComponent() {
  const { user } = useAuthenticator();
  
  return <p>Hello, {user?.username}</p>;
}
```

Sign out:

```typescript
const { signOut } = useAuthenticator();

<button onClick={() => signOut()}>Sign Out</button>
```

## Common Patterns

### Form with Loading State

```typescript
function SettingsForm() {
  const [values, setValues] = useState({ email: '' });
  const updateSettings = useUpdateSettings();

  const handleSubmit = () => {
    updateSettings.mutate(values);
  };

  return (
    <>
      <input 
        value={values.email}
        onChange={(e) => setValues({ ...values, email: e.target.value })}
      />
      <button 
        onClick={handleSubmit}
        disabled={updateSettings.isPending}
      >
        {updateSettings.isPending ? 'Saving...' : 'Save'}
      </button>
    </>
  );
}
```

### Conditional Rendering

```typescript
{isLoading && <LoadingSkeleton />}

{error && <ErrorMessage error={error} />}

{data?.items.length === 0 && <EmptyState />}

{data && <JobList jobs={data.items} />}
```

### URL State Sync

```typescript
function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  
  const filters = {
    search: searchParams.get('search') || undefined,
    status: searchParams.get('status') as any,
  };

  const updateFilters = (newFilters: JobFilters) => {
    const params = new URLSearchParams();
    if (newFilters.search) params.set('search', newFilters.search);
    if (newFilters.status) params.set('status', newFilters.status);
    setSearchParams(params);
  };

  return <FilterBar filters={filters} onChange={updateFilters} />;
}
```

## Testing

Currently, no testing setup. To add tests:

```bash
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom
```

Create `src/__tests__/components/JobCard.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { JobCard } from '@/components/JobCard';

describe('JobCard', () => {
  it('renders job title', () => {
    const job = { /* mock job */ };
    render(<JobCard job={job} />);
    expect(screen.getByText(job.roleName)).toBeInTheDocument();
  });
});
```

## Performance Tips

1. **Use React.memo for expensive components**:

```typescript
const MemoizedJobCard = React.memo(JobCard);
```

2. **Memoize callbacks**:

```typescript
const handleClick = useCallback(() => {
  // ...
}, [dependencies]);
```

3. **Lazy load route components**:

```typescript
const Dashboard = lazy(() => import('@/pages/Dashboard'));
```

4. **Check React DevTools Profiler** for slow components

5. **Use React Query DevTools** to monitor queries

## Debugging

### Browser DevTools

1. **Console**: Check for errors and warnings
2. **Network**: Verify API requests, check response sizes
3. **Performance**: Record and analyze rendering
4. **React DevTools**: Inspect component tree, hooks

### React Query DevTools

Add to `src/main.tsx`:

```typescript
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <App />
    <ReactQueryDevtools initialIsOpen={false} />
  </QueryClientProvider>,
);
```

Then open DevTools and click React Query tab.

### Amplify Debugging

```typescript
import { enableDebugLogging } from 'aws-amplify';
enableDebugLogging();
```

Check browser console for Amplify logs.

## Common Issues & Solutions

### Issue: "Cannot find module '@/...'"

**Solution**: Ensure vite.config.ts has path alias:

```typescript
alias: {
  '@': path.resolve(__dirname, './src'),
}
```

### Issue: Changes not reflecting

**Solution**: Vite HMR may fail. Hard refresh browser (Cmd+Shift+R or Ctrl+Shift+R)

### Issue: API returns 401

**Solution**: 
1. Check VITE_API_URL is correct
2. Ensure Cognito token is being attached (check Network tab)
3. Verify backend CORS allows localhost:5173

### Issue: Form values not updating

**Solution**: Ensure state update is correct:

```typescript
// Good
setState(prev => ({ ...prev, field: newValue }));

// Or
setState({ ...state, field: newValue });

// Bad (missing spread)
setState({ field: newValue });
```

## Code Review Checklist

Before submitting code:

- [ ] All TypeScript types are correct (no `any`)
- [ ] Components have Props interfaces
- [ ] Imports use `@/` path aliases
- [ ] Styles use Tailwind classes only
- [ ] React Query hooks used for data
- [ ] Error states handled
- [ ] Loading states shown
- [ ] Mobile responsive (test at 640px)
- [ ] No console warnings/errors
- [ ] Linter passes: `npm run lint`
- [ ] Code formatted: `npx prettier --write .`

## Adding Dependencies

Before adding a package:

1. **Check if Tailwind has it**: Most UI needs → use Tailwind
2. **Check alternatives**: Is there a smaller package?
3. **Get approval**: Discuss with team first
4. **Add to package.json**: `npm install <package>`
5. **Update lock file**: Commit `package-lock.json`
6. **Document**: Add to this guide if it's significant

Example good additions:
- lucide-react ✅ (icons)
- react-hook-form ❓ (add if forms get complex)
- @sentry/react ❓ (add in production)

Example bad additions:
- moment.js ❌ (use date-fns instead)
- lodash ❌ (use native JS)
- Bootstrap ❌ (use Tailwind)

## Resources

- **React Docs**: https://react.dev
- **TypeScript**: https://www.typescriptlang.org/docs/
- **Tailwind CSS**: https://tailwindcss.com
- **React Router**: https://reactrouter.com/
- **React Query**: https://tanstack.com/query/latest
- **Vite**: https://vitejs.dev
- **Amplify**: https://docs.amplify.aws

## Support

Questions? Check:

1. README.md for architecture overview
2. API.md for API integration details
3. Browser DevTools for runtime errors
4. React/TypeScript docs for language features
5. Team documentation or Slack

---

Happy coding! Feel free to reach out with questions.
