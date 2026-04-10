# Scout Frontend Documentation Index

Welcome to Scout! This document helps you navigate all the documentation.

## Start Here

### For First-Time Setup (5 minutes)
👉 **Read**: [QUICK_START.md](QUICK_START.md)
- Install dependencies
- Configure environment variables
- Start development server
- Login and test the app

### For Project Overview
👉 **Read**: [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
- What was built
- Technology stack
- File breakdown
- Key accomplishments

## Development

### For Understanding the Code
👉 **Read**: [README.md](README.md)
- Architecture overview
- Project structure
- Features breakdown
- React Query patterns
- Tailwind theme

### For Writing Code
👉 **Read**: [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
- Code organization principles
- Component patterns
- Adding new features
- Testing strategies
- Debugging tips
- Common issues & solutions

### For API Integration
👉 **Read**: [API.md](API.md)
- Endpoint reference
- Request/response formats
- Authentication details
- Error handling
- React Query caching
- Performance optimization

## Deployment

### For Production Deployment
👉 **Read**: [DEPLOYMENT.md](DEPLOYMENT.md)
- Build process
- S3 + CloudFront setup
- Environment-specific builds
- Performance considerations
- Monitoring & rollback
- Security checklist
- Post-deployment verification

## Reference

### File Inventory
👉 **Read**: [FILES_CREATED.md](FILES_CREATED.md)
- Complete list of all 35 files
- File organization
- Code statistics
- Technology choices

## Quick Navigation

### By Role

**Product Manager/Non-Technical**
1. [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - What was built
2. [DEPLOYMENT.md](DEPLOYMENT.md) - How to deploy

**New Developer**
1. [QUICK_START.md](QUICK_START.md) - Get it running
2. [README.md](README.md) - Understand the architecture
3. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Write code

**Full-Stack Developer**
1. [README.md](README.md) - Architecture
2. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Code patterns
3. [API.md](API.md) - API integration
4. [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment

**DevOps/SRE**
1. [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment procedures
2. [README.md](README.md) - Performance notes
3. [API.md](API.md) - API integration details

### By Task

**I want to...**

- [**Get it running locally**](QUICK_START.md) → QUICK_START.md
- [**Understand the code structure**](README.md) → README.md
- [**Add a new component**](DEVELOPER_GUIDE.md#adding-a-new-feature) → DEVELOPER_GUIDE.md
- [**Fix a bug**](DEVELOPER_GUIDE.md#debugging) → DEVELOPER_GUIDE.md
- [**Integrate with the API**](API.md) → API.md
- [**Deploy to production**](DEPLOYMENT.md) → DEPLOYMENT.md
- [**Optimize performance**](DEPLOYMENT.md#performance-considerations) → DEPLOYMENT.md
- [**Set up CI/CD**](DEPLOYMENT.md#automated-deployment-cicd) → DEPLOYMENT.md
- [**Debug authentication**](DEVELOPER_GUIDE.md#amplify-debugging) → DEVELOPER_GUIDE.md
- [**Find a specific file**](FILES_CREATED.md) → FILES_CREATED.md

## Documentation Structure

```
Documentation/
├── INDEX.md                    # You are here
├── QUICK_START.md             # 5-minute setup guide
├── PROJECT_SUMMARY.md         # Project overview
├── README.md                  # Full documentation
├── DEVELOPER_GUIDE.md         # Code patterns & development
├── API.md                     # API integration
├── DEPLOYMENT.md              # Production deployment
└── FILES_CREATED.md           # File inventory
```

## Technology Quick Reference

| Need | Answer |
|------|--------|
| **Framework** | React 18 with TypeScript |
| **Routing** | React Router v6 |
| **API** | Fetch with Amplify auth tokens |
| **Styling** | Tailwind CSS |
| **Icons** | Lucide React |
| **State** | React Query v5 |
| **Auth** | AWS Cognito via Amplify UI |
| **Build** | Vite |
| **Dates** | date-fns |

## Common Commands

```bash
# Setup
npm install
cp .env.example .env
# Edit .env with credentials

# Development
npm run dev              # Start dev server (HMR)
npm run build           # Production build
npm run preview         # Preview build locally

# Code Quality
npm run lint            # Check code with ESLint
npx prettier --write .  # Format code
```

## Key Features at a Glance

- ✅ Job listing from 5 sources (LinkedIn, Indeed, Glassdoor, etc.)
- ✅ Advanced filtering (date, rating, status, search, sort)
- ✅ Pagination with configurable page size
- ✅ Application status tracking (6 statuses)
- ✅ User authentication (Cognito + MFA)
- ✅ Email notification settings
- ✅ Responsive mobile design
- ✅ Dark mode ready (future)
- ✅ Glassdoor rating integration
- ✅ Salary range display

## Environment Variables

```env
VITE_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_USER_POOL_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX
VITE_API_URL=https://api.scout.carniaux.io/v1
```

Get these from:
- Cognito User Pool console (USER_POOL_ID, CLIENT_ID)
- Backend API documentation (API_URL)

## Project Stats

- **Total Files**: 35
- **Source Code**: ~1,800 lines
- **Components**: 8
- **Pages**: 2
- **Hooks**: 5
- **Documentation**: ~50KB
- **Build Time**: <2 seconds
- **Bundle Size**: ~270KB gzipped

## Troubleshooting Quick Links

| Issue | Solution |
|-------|----------|
| "Cannot find module '@/...'" | [DEVELOPER_GUIDE.md#issue-cannot-find-module](DEVELOPER_GUIDE.md#issue-cannot-find-module) |
| Blank white screen | [QUICK_START.md#blank-white-screen-on-load](QUICK_START.md#blank-white-screen-on-load) |
| Cannot login | [QUICK_START.md#cannot-login](QUICK_START.md#cannot-login) |
| API returns 401 | [QUICK_START.md#api-returns-401-unauthorized](QUICK_START.md#api-returns-401-unauthorized) |
| Slow performance | [QUICK_START.md#slow-performance](QUICK_START.md#slow-performance) |

## Getting Help

1. **Check the docs** - Most answers are in the documentation
2. **Search DevTools** - Browser Console shows errors and hints
3. **Review code patterns** - Look at existing components
4. **Check API responses** - Network tab shows API issues
5. **Read error messages** - React and TypeScript provide helpful hints

## Next Steps

1. **New here?** Start with [QUICK_START.md](QUICK_START.md)
2. **Understand structure?** Read [README.md](README.md)
3. **Ready to code?** Follow [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
4. **Need to deploy?** Check [DEPLOYMENT.md](DEPLOYMENT.md)
5. **Integrating API?** See [API.md](API.md)

## Document Sizes & Read Times

| Document | Size | Read Time |
|----------|------|-----------|
| [QUICK_START.md](QUICK_START.md) | 3 KB | 5 min |
| [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | 4 KB | 8 min |
| [README.md](README.md) | 6 KB | 15 min |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | 10 KB | 20 min |
| [API.md](API.md) | 8 KB | 15 min |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 9 KB | 20 min |
| [FILES_CREATED.md](FILES_CREATED.md) | 4 KB | 8 min |

**Total**: ~44 KB, ~90 minutes to read all

## Tips for Navigation

- **Ctrl+F** (Cmd+F on Mac) to search within documents
- **Use links** in documentation to jump between sections
- **Check headers** - Documents are organized with clear sections
- **Read bold text** - Key concepts are highlighted
- **Review code examples** - Real patterns are shown

## Version & Updates

- **Frontend Version**: 0.1.0
- **Created**: 2026-04-09
- **Status**: Production Ready
- **Last Updated**: Now

## Support & Feedback

For issues or improvements:
1. Check existing documentation first
2. Review the browser console for errors
3. Consult DEVELOPER_GUIDE.md for patterns
4. Search API.md for endpoint details

---

**Let's build Scout!** 🚀

Start with [QUICK_START.md](QUICK_START.md) and come back here if you need to find something.
