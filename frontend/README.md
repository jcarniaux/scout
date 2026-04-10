# Scout Frontend

A modern React 18 application for the Scout job aggregation platform. Built with TypeScript, Tailwind CSS, and AWS Amplify for authentication.

## Architecture

- **Framework**: React 18 + TypeScript
- **Styling**: Tailwind CSS with custom Scout theme
- **Routing**: React Router v6
- **State Management**: React Query (TanStack Query v5) for server state
- **Authentication**: AWS Cognito via Amplify UI
- **API**: Fetch with Amplify auth tokens
- **Icons**: Lucide React
- **Dates**: date-fns

## Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── Navbar.tsx       # Top navigation bar
│   ├── FilterBar.tsx    # Job filtering controls
│   ├── JobCard.tsx      # Individual job card
│   ├── JobList.tsx      # Job list with pagination
│   ├── StatusBadge.tsx  # Application status badge
│   ├── StatusSelect.tsx # Status dropdown
│   ├── RatingBadge.tsx  # Glassdoor rating display
│   └── EmptyState.tsx   # Empty state UI
├── pages/               # Page components
│   ├── Dashboard.tsx    # Main job listing page
│   └── Settings.tsx     # User settings page
├── hooks/               # Custom React hooks
│   └── useJobs.ts       # React Query hooks for jobs & settings
├── services/            # API client
│   └── api.ts          # Authenticated API calls
├── types/               # TypeScript type definitions
│   └── index.ts        # Job, User, and Filter types
├── App.tsx              # Root app component with routing
├── main.tsx             # React DOM entry point
├── index.css            # Global styles & Tailwind directives
└── amplifyconfiguration.ts # Amplify config from env vars
```

## Environment Variables

Create a `.env` file in the frontend root (copy from `.env.example`):

```env
VITE_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_USER_POOL_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX
VITE_API_URL=https://XXXXXXXXXX.execute-api.us-east-1.amazonaws.com/v1
```

## Installation & Setup

```bash
# Install dependencies
npm install

# Start development server (Vite)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Run linting
npm run lint
```

## Key Features

### Authentication
- Cognito integration via @aws-amplify/ui-react
- Automatic login/signup/MFA enrollment UI
- TOTP-based multi-factor authentication support
- Auth tokens automatically attached to API requests

### Job Management
- **Filter Jobs**: By date range, Glassdoor rating, application status, and search
- **Sort**: By most recent, highest salary, or best rating
- **Pagination**: Configurable page size (10, 20, 50 items per page)
- **Status Tracking**: Track applications across 6 statuses (Not Applied → Offer Accepted)

### Job Card Details
- Role name & company
- Glassdoor rating with color coding (red <3.0, yellow 3.0-4.0, green ≥4.0)
- Location with map-pin icon
- Salary range or "Not disclosed"
- Benefits: PTO, sick days, 401(k) match, other benefits
- Posted date (relative: "2 days ago")
- Source badge (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice)
- Application status dropdown with color-coded options
- Direct link to job posting

### Settings
- Email notification preferences
- Toggle daily/weekly report emails
- Read-only email display from Cognito
- Save with success/error feedback

### URL State Sync
- Filters persist in URL search params
- Refreshing the page preserves filter state
- Shareable URLs with filters pre-applied

## API Integration

The app communicates with the Scout backend API using authenticated fetch requests:

```typescript
// All requests automatically include Cognito ID token in Authorization header
api.getJobs(filters, page, pageSize)
api.getJob(jobId)
api.updateStatus(jobId, status, notes?)
api.getSettings()
api.updateSettings(settings)
```

## React Query Hooks

```typescript
// Hooks are in src/hooks/useJobs.ts
useJobs(filters, page, pageSize)        // Query jobs
useJob(jobId)                           // Query single job
useUpdateStatus()                       // Mutation: update job status
useSettings()                           // Query user settings
useUpdateSettings()                     // Mutation: update settings
```

Queries auto-invalidate on mutations, and responses are cached for 5-10 minutes.

## Tailwind Theme

Scout uses a blue/slate color palette:

```
Primary: #2563eb (blue-600)
Surface: #f9fafb (slate-50)
Border: #e2e8f0 (slate-200)
```

All components use Tailwind utility classes exclusively. See `tailwind.config.js` for theme extensions.

## Responsive Design

- Mobile-first approach
- Hamburger menu on devices <768px (md breakpoint)
- Responsive grid layouts
- Touch-friendly button sizes

## Browser Support

- Modern browsers (ES2020+)
- Chrome, Firefox, Safari, Edge
- Mobile browsers (iOS Safari, Chrome Mobile)

## Development Tips

### Hot Module Replacement
Vite provides HMR out of the box. Changes to components instantly reload without losing state.

### TypeScript Strict Mode
Strict mode is enabled. All types must be explicit—no implicit `any`.

### Path Aliases
Use `@/` to import from `src/`:
```typescript
import { api } from '@/services/api'
import { Dashboard } from '@/pages/Dashboard'
```

### Debugging
- React DevTools browser extension
- Amplify DevTools for auth debugging
- React Query DevTools (can be added via `@tanstack/react-query-devtools`)

## Performance Optimizations

- React Query caching reduces unnecessary API calls
- Pagination limits data per page
- Lazy loading via React Router code splitting (can be added)
- Tailwind CSS purges unused styles in production

## Known Limitations & Future Enhancements

- Job notes are limited to 2 lines (line-clamp-2)
- Bulk actions not implemented yet
- Email preferences are simple on/off (no frequency customization)
- Dark mode toggle not implemented
- Offline support not implemented

## Troubleshooting

### "Cannot find module '@/...'"
Ensure the vite.config.ts path alias is configured correctly.

### Blank page on load
Check that Cognito credentials are correctly set in .env and that the User Pool exists in AWS.

### API calls failing with 401
Ensure the Cognito token is being fetched correctly. Check browser console for auth errors.

### Tailwind styles not applying
Verify postcss.config.js and tailwind.config.js paths match your source structure. Restart dev server if needed.

## License

Private project for Scout job aggregation platform.
