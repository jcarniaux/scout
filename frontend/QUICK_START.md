# Scout Frontend Quick Start

Get the Scout job aggregation platform running locally in 5 minutes.

## Prerequisites

- Node.js 18+ ([Download](https://nodejs.org/))
- npm 9+ (included with Node.js)
- AWS account with Cognito User Pool configured
- Scout backend API running

## 1. Setup

```bash
cd frontend
npm install
```

## 2. Configure Environment

Copy `.env.example` to `.env` and update with your AWS values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
VITE_USER_POOL_ID=us-east-1_XXXXXXXXX        # From Cognito console
VITE_USER_POOL_CLIENT_ID=XXXXXXXXXXXXXXXXX   # From Cognito app client
VITE_API_URL=http://localhost:3000/v1        # Your backend API URL
```

## 3. Start Development Server

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

## 4. Login

The Amplify login screen appears automatically. To create an account:

1. Click "Create account"
2. Enter email and password (password must meet complexity requirements)
3. Verify your email via the link in your inbox
4. You may be prompted to set up TOTP MFA
5. Dashboard loads with job listings

## What's Included

### Pages

- **Dashboard** (`/`) - Job listings with filters, sorting, and pagination
- **Settings** (`/settings`) - Email notification preferences

### Components

- Job cards with Glassdoor ratings, salary ranges, benefits
- Advanced filtering (date, rating, status, search)
- Application status tracking (6 statuses from Not Applied to Offer Accepted)
- Responsive mobile design

### Features

- ✅ AWS Cognito authentication with MFA support
- ✅ React Query for intelligent caching
- ✅ Tailwind CSS with Scout brand colors
- ✅ URL state persistence (filters survive refresh)
- ✅ Pagination with configurable page size
- ✅ Dark mode support (future)

## Project Structure

```
src/
├── components/      # UI components (JobCard, FilterBar, etc.)
├── pages/          # Full pages (Dashboard, Settings)
├── hooks/          # React Query hooks (useJobs, useSettings)
├── services/       # API client (authenticated fetch)
├── types/          # TypeScript definitions
├── App.tsx         # Root component with routing
└── main.tsx        # React DOM entry point
```

## Common Commands

```bash
# Development
npm run dev              # Start dev server with HMR

# Production
npm run build           # Build optimized bundle
npm run preview         # Preview production build locally

# Code Quality
npm run lint            # Check code with ESLint
npx prettier --write .  # Format code

# Dependencies
npm update              # Update packages
npm audit               # Check security vulnerabilities
```

## Environment Variables Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `VITE_USER_POOL_ID` | Cognito User Pool ID | `us-east-1_abc123xyz` |
| `VITE_USER_POOL_CLIENT_ID` | Cognito app client ID | `3abc123def456ghi789` |
| `VITE_API_URL` | Scout backend API base URL | `http://localhost:3000/v1` |

## Troubleshooting

### "Cannot find module '@/...'"

The path alias `@/` maps to `src/`. Ensure vite.config.ts has correct paths.

### Blank white screen on load

1. Open browser DevTools Console (F12)
2. Check for JavaScript errors
3. Verify .env variables are set
4. Ensure Cognito User Pool ID is correct

### Cannot login

1. Verify VITE_USER_POOL_ID and VITE_USER_POOL_CLIENT_ID are correct
2. Ensure Cognito User Pool exists and app client is enabled
3. Check that TOTP MFA setup doesn't require additional configuration
4. Review browser console for error messages

### API returns 401 (Unauthorized)

1. Ensure VITE_API_URL is correct
2. Verify backend API allows CORS from localhost:5173
3. Check that Cognito tokens are being attached to requests
4. Tokens may be expired; try logging out and back in

### Slow performance

1. Check React Query DevTools (if added) for cache hits
2. Verify API responses are reasonably sized (pagination)
3. Open DevTools Network tab and sort by size
4. Check for network waterfall delays

## Next Steps

### For Development

1. **Review components** in `src/components/` to understand the UI layer
2. **Check hooks** in `src/hooks/useJobs.ts` for data management patterns
3. **Explore API integration** in `src/services/api.ts`
4. **Read documentation** in README.md, API.md, DEPLOYMENT.md

### For Deployment

1. **Build locally**: `npm run build` and test with `npm run preview`
2. **Set production env vars** with your backend API URL
3. **Follow DEPLOYMENT.md** for S3 + CloudFront setup
4. **Test thoroughly** on staging before production

### To Customize

- **Colors**: Edit `tailwind.config.js` theme section
- **Fonts**: Add to Tailwind config or index.css
- **Layout**: Modify component Tailwind classes
- **API integration**: Update `src/services/api.ts`

## Tech Stack Summary

| Layer | Technology |
|-------|------------|
| **Framework** | React 18 + TypeScript |
| **Routing** | React Router v6 |
| **State** | React Query v5 |
| **Auth** | AWS Cognito + Amplify UI |
| **Styling** | Tailwind CSS |
| **Icons** | Lucide React |
| **Dates** | date-fns |
| **Build** | Vite |
| **Linting** | ESLint + Prettier |

## Architecture Decisions

- **React Query**: Simplifies server state management, automatic caching, optimistic updates
- **Tailwind CSS**: Utility-first approach, minimal CSS file size, excellent for responsive design
- **Amplify UI**: Pre-built auth components, handles MFA enrollment automatically
- **Vite**: Fast HMR, instant cold start, optimized production builds

## Resources

- [React Docs](https://react.dev)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)
- [Tailwind CSS](https://tailwindcss.com)
- [AWS Amplify](https://docs.amplify.aws)
- [React Query](https://tanstack.com/query/latest)
- [Vite Guide](https://vitejs.dev/guide/)

## Support

For issues:

1. Check browser console for JavaScript errors
2. Review DevTools Network tab for API failures
3. Verify environment variables in `.env`
4. Check that backend API is running and accessible
5. Review documentation files (README.md, API.md, DEPLOYMENT.md)

## What's Next?

After getting comfortable with the codebase:

- [ ] Implement dark mode toggle
- [ ] Add job details modal/page
- [ ] Implement job notes editing
- [ ] Add saved searches / favorites
- [ ] Implement bulk actions (status updates)
- [ ] Add export to CSV functionality
- [ ] Implement OAuth social login
- [ ] Add job salary comparison charts
- [ ] Implement advanced search operators
- [ ] Add email digest preview

---

**Happy coding!** Build Scout into an amazing job tracking tool.
