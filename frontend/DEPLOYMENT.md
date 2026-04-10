# Scout Frontend Deployment Guide

## Build & Deployment Overview

The Scout frontend is deployed on AWS, served via CloudFront CDN at https://scout.carniaux.io.

## Prerequisites

- Node.js 18+ and npm
- AWS CLI configured with credentials
- S3 bucket for static assets
- CloudFront distribution configured
- Environment variables set up

## Build Process

### Local Build

```bash
# Install dependencies
npm install

# Build for production
npm run build
```

Output: `dist/` directory containing optimized bundle

### Build Configuration

- **Vite**: Fast build with CSS/JS minification
- **TypeScript**: Strict type checking
- **Tailwind**: Purges unused CSS styles
- **Output**: Precompressed with gzip

## Environment Variables

### Required for Build

Create `.env` file with:

```env
VITE_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_USER_POOL_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX
VITE_API_URL=https://api.scout.carniaux.io/v1
```

**NOTE**: These are embedded at build time. For different environments (dev/staging/prod), rebuild with different .env files.

## Deployment Steps

### 1. Build Locally

```bash
npm run build
```

### 2. Upload to S3

```bash
# Upload dist folder to S3
aws s3 sync dist/ s3://scout-frontend/ --delete --cache-control "public, max-age=31536000" --exclude "*.html"

# HTML files with no-cache for instant updates
aws s3 cp dist/index.html s3://scout-frontend/ --cache-control "no-cache, no-store, must-revalidate" --content-type "text/html; charset=utf-8"
```

### 3. Invalidate CloudFront

```bash
# Clear CDN cache to serve new version immediately
aws cloudfront create-invalidation --distribution-id E3XXXXX --paths "/*"
```

## Automated Deployment (CI/CD)

For GitHub Actions / similar CI tools:

```yaml
name: Deploy Scout Frontend
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: npm ci
      - run: npm run build
      - uses: aws-actions/configure-aws-credentials@v2
      - run: aws s3 sync dist/ s3://scout-frontend/ --delete
      - run: aws cloudfront create-invalidation --distribution-id E3XXXXX --paths "/*"
```

## Environment-Specific Builds

### Development

```bash
VITE_API_URL=http://localhost:3000/v1 npm run build
```

### Staging

```bash
VITE_API_URL=https://staging-api.scout.carniaux.io/v1 npm run build
```

### Production

```bash
VITE_API_URL=https://api.scout.carniaux.io/v1 npm run build
```

## Performance Considerations

### Bundle Size

- React: ~42KB (gzipped)
- React Router: ~6KB
- React Query: ~15KB
- Tailwind: ~20KB (purged)
- Amplify: ~60KB
- Total: ~143KB gzipped

### Caching Strategy

- **Assets** (JS/CSS): 1 year cache + content hash
- **HTML**: No cache (always fetch latest)
- **CloudFront**: 1 hour TTL for HTML

### Optimizations

- Tree-shaking removes unused code
- Dynamic imports for large components (future)
- CSS purging via Tailwind
- Image optimization (if added)

## Monitoring & Rollback

### Check Deployment

```bash
# Test CloudFront distribution
curl -I https://scout.carniaux.io

# Verify API endpoints are reachable
curl https://api.scout.carniaux.io/health
```

### Rollback

If issues arise, revert to previous S3 version:

```bash
# List S3 versions (if versioning enabled)
aws s3api list-object-versions --bucket scout-frontend

# Or deploy previous known-good build
git checkout <previous-commit>
npm run build
aws s3 sync dist/ s3://scout-frontend/ --delete
```

## Troubleshooting

### 404 on refresh (SPA routing)

CloudFront S3 origin must forward all non-asset routes to index.html:

```bash
# Add CloudFront error page rule
# 404 → /index.html (HTTP 200)
```

### CORS errors to API

Ensure API at VITE_API_URL has CORS headers:

```
Access-Control-Allow-Origin: https://scout.carniaux.io
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, Authorization
```

### Blank white screen

1. Check browser console for JS errors
2. Verify .env variables were embedded: `grep VITE_ dist/assets/*.js`
3. Check CloudFront error logs in CloudWatch

### Slow load times

1. Check CloudFront cache hit ratio (should be >90%)
2. Verify gzip compression enabled in S3
3. Monitor API response times
4. Check React Query query timings

## Security

### Content Security Policy

Add to S3 bucket metadata or CloudFront headers:

```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https:; connect-src 'self' https://api.scout.carniaux.io https://cognito-idp.us-east-1.amazonaws.com
```

### HTTPS Only

CloudFront should:
- Redirect HTTP → HTTPS
- Enforce TLS 1.2+
- Use modern ciphers

### Environment Variables

**NEVER** commit `.env` files. Use:
- AWS Secrets Manager (production)
- GitHub Secrets (CI/CD)
- Local .env.local (git-ignored)

## Version Management

Track deployed versions:

```bash
# Tag releases
git tag v0.1.0
git push origin v0.1.0

# Update version in package.json
npm version minor
npm run build
# Deploy...
```

## Performance Budgets

Suggested limits for each build artifact:

- JS bundle: <200KB gzipped
- CSS bundle: <50KB gzipped
- HTML: <20KB
- Total: <270KB gzipped

Monitor with:

```bash
npm install --save-dev bundlesize
```

## Logs & Monitoring

### CloudFront Logs

Enable CloudFront access logs to S3 for debugging HTTP errors and cache performance.

### Application Errors

Add Sentry or similar error tracking:

```typescript
// In src/main.tsx
import * as Sentry from "@sentry/react";
Sentry.init({
  dsn: "https://...",
  environment: "production",
});
```

## Post-Deployment Checklist

- [ ] Build succeeds locally without warnings
- [ ] .env variables correctly embedded
- [ ] S3 bucket contains latest dist/
- [ ] CloudFront invalidation complete
- [ ] https://scout.carniaux.io accessible
- [ ] Login flow works (Cognito)
- [ ] Dashboard loads job data from API
- [ ] Filters persist in URL
- [ ] Settings page accessible
- [ ] Mobile responsive layout works
- [ ] No JavaScript errors in console
- [ ] API calls include Authorization header
- [ ] Performance metrics acceptable

## Support & Troubleshooting

For issues, check:
1. Browser DevTools Console for errors
2. CloudFront logs in CloudWatch
3. API gateway logs for 5xx errors
4. AWS Cognito sign-in logs
5. S3 bucket policy and CORS settings
