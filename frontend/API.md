# Scout Frontend API Integration

## Overview

The Scout frontend communicates with the backend API for job data, user authentication, and settings management. All API requests are authenticated using AWS Cognito ID tokens.

## Base URL

```
${VITE_API_URL}
```

Example: `https://api.scout.carniaux.io/v1`

## Authentication

All requests include the Cognito ID token in the Authorization header:

```
Authorization: Bearer <cognito-id-token>
```

Tokens are automatically fetched using the Amplify `fetchAuthSession()` function and managed by the `api.ts` service layer.

## Endpoints

### Jobs

#### Get Jobs (Paginated)

```
GET /jobs?dateRange=7d&minRating=3.5&status=APPLIED&search=python&sort=date&page=1&pageSize=20
```

**Query Parameters:**

| Parameter | Type | Optional | Description |
|-----------|------|----------|-------------|
| dateRange | string | Yes | Filter by posting date: `24h`, `7d`, or `30d` |
| minRating | number | Yes | Minimum Glassdoor rating (1.0-5.0) |
| status | string | Yes | Application status filter |
| search | string | Yes | Search jobs by role, company, or location |
| sort | string | Yes | Sort order: `date`, `salary`, or `rating` |
| page | number | No | Page number (1-indexed) |
| pageSize | number | No | Items per page (10-100) |

**Response:**

```typescript
{
  "items": [
    {
      "jobId": "abc123def456",
      "roleName": "Senior Software Engineer",
      "company": "Acme Corp",
      "location": "San Francisco, CA",
      "salaryMin": 180000,
      "salaryMax": 220000,
      "ptoDays": 20,
      "sickDays": 10,
      "match401k": "6%",
      "benefits": "Health, dental, vision, stock options",
      "postedDate": "2024-01-15T09:30:00Z",
      "sourceUrl": "https://linkedin.com/jobs/123",
      "source": "linkedin",
      "glassdoorRating": 4.2,
      "glassdoorUrl": "https://glassdoor.com/Overview/Working-at-Acme-Corp-EI_IE1234.11,20.htm",
      "createdAt": "2024-01-15T10:00:00Z",
      "applicationStatus": "APPLIED",
      "notes": "Referred by John Doe"
    }
  ],
  "totalCount": 342,
  "page": 1,
  "pageSize": 20,
  "hasMore": true
}
```

**Status Codes:**

- `200 OK` - Success
- `400 Bad Request` - Invalid parameters
- `401 Unauthorized` - Invalid or expired token
- `500 Internal Server Error` - Server error

#### Get Single Job

```
GET /jobs/{jobId}
```

**Response:**

```typescript
{
  "jobId": "abc123def456",
  "roleName": "Senior Software Engineer",
  // ... same fields as above
}
```

#### Update Job Status

```
PATCH /jobs/{jobId}/status
Content-Type: application/json

{
  "status": "TECHNICAL_INTERVIEW",
  "notes": "Passed initial screening, scheduled for final round"
}
```

**Valid Status Values:**

- `NOT_APPLIED`
- `APPLIED`
- `RECRUITER_INTERVIEW`
- `TECHNICAL_INTERVIEW`
- `OFFER_RECEIVED`
- `OFFER_ACCEPTED`

**Response:**

```typescript
{
  "jobId": "abc123def456",
  "applicationStatus": "TECHNICAL_INTERVIEW",
  "notes": "Passed initial screening, scheduled for final round",
  "updatedAt": "2024-01-20T14:30:00Z"
}
```

### User Settings

#### Get User Settings

```
GET /user/settings
```

**Response:**

```typescript
{
  "email": "user@example.com",
  "dailyReport": true,
  "weeklyReport": false
}
```

#### Update User Settings

```
PUT /user/settings
Content-Type: application/json

{
  "email": "user@example.com",
  "dailyReport": true,
  "weeklyReport": false
}
```

**Response:**

```typescript
{
  "email": "user@example.com",
  "dailyReport": true,
  "weeklyReport": false,
  "updatedAt": "2024-01-20T14:30:00Z"
}
```

## Frontend Implementation

### API Service (`src/services/api.ts`)

The `api` object provides typed wrappers around all API endpoints:

```typescript
import { api } from '@/services/api';

// Get jobs
const response = await api.getJobs(
  { search: 'python', sort: 'salary' },
  1,  // page
  20  // pageSize
);

// Update job status
await api.updateStatus('jobId123', 'APPLIED', 'Submitted application');

// Get settings
const settings = await api.getSettings();

// Update settings
await api.updateSettings({
  email: 'user@example.com',
  dailyReport: true,
  weeklyReport: false,
});
```

### React Query Hooks (`src/hooks/useJobs.ts`)

Use React Query hooks for automatic caching, refetching, and state management:

```typescript
import { useJobs, useUpdateStatus, useSettings, useUpdateSettings } from '@/hooks/useJobs';

// In a component:
function JobListComponent() {
  const filters = { search: 'python' };
  const { data, isLoading, error } = useJobs(filters, 1, 20);
  
  const updateStatus = useUpdateStatus();
  const handleStatusChange = (jobId, status) => {
    updateStatus.mutate({ jobId, status });
  };
}
```

## Error Handling

### API Errors

The `api.ts` service throws errors for non-2xx responses:

```typescript
try {
  await api.getJobs(filters);
} catch (error) {
  if (error instanceof Error) {
    console.error(`API error: ${error.message}`);
  }
}
```

### React Query Error Handling

Errors are automatically caught and exposed via the `error` property:

```typescript
const { data, error, isLoading } = useJobs(filters);

if (error) {
  return <ErrorMessage error={error} />;
}
```

### Authentication Errors

If a 401 is returned, Amplify automatically redirects to the login page.

## Caching Strategy

### Query Caching

Jobs and settings are cached for 5-10 minutes. Manual refresh:

```typescript
const { refetch } = useJobs(filters);
refetch();
```

### Mutation Side Effects

Mutations automatically invalidate related queries:

```typescript
const updateStatus = useUpdateStatus();
// After mutation completes, all useJobs queries refetch automatically
updateStatus.mutate({ jobId, status });
```

## Rate Limiting

If the API implements rate limiting, responses will include:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1234567890
```

Handle gracefully in production.

## Testing

### Mock API for Development

Create a mock service in `src/services/api.mock.ts`:

```typescript
export const mockApi = {
  getJobs: async () => ({
    items: [/* mock jobs */],
    totalCount: 10,
    page: 1,
    pageSize: 20,
    hasMore: false,
  }),
  // ... other mocked endpoints
};
```

Use environment variable to toggle:

```typescript
const api = import.meta.env.MODE === 'test' ? mockApi : realApi;
```

### API Contract Testing

Ensure your API responses match the `Job` and `PaginatedResponse` types:

```typescript
import { Job, PaginatedResponse } from '@/types';

const validateResponse = (data: unknown): PaginatedResponse<Job> => {
  // TypeScript ensures type safety
  return data as PaginatedResponse<Job>;
};
```

## Performance

### Pagination

Always paginate large result sets:

```typescript
// Good: Paginate
useJobs(filters, 1, 20);  // Returns first 20 results

// Bad: Don't request all at once
useJobs(filters, 1, 10000);  // Inefficient
```

### Filter Optimization

Apply filters at the API level, not client-side:

```typescript
// Good: Filter on server
useJobs({ search: 'python', minRating: 4.0 });

// Bad: Get all, filter in JS
const jobs = useJobs({});
const filtered = jobs.filter(j => j.company === 'Acme');
```

### Avoid Waterfalls

Use React Query's dependency tracking to avoid cascading requests:

```typescript
// Good: Parallel queries
const jobsQuery = useJobs(filters);
const settingsQuery = useSettings();

// Bad: Waterfall (settings waits for jobs)
const jobs = useJobs(filters);
const settings = useSettings(jobs.data?.userId); // Don't do this
```

## Debugging

### Enable Network Logging

```typescript
// In api.ts, before fetch:
console.log(`${method} ${url}`, options);
```

### React Query DevTools

Add to main.tsx:

```typescript
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';

<QueryClientProvider client={queryClient}>
  <App />
  <ReactQueryDevtools initialIsOpen={false} />
</QueryClientProvider>
```

### API Response Validation

In development, validate all responses:

```typescript
if (import.meta.env.DEV) {
  const validated = validateResponse(data);
  console.log('API response valid:', validated);
}
```

## Versioning

API is versioned via `/v1` in the URL. Future breaking changes will use `/v2`, etc.

Frontend should handle multiple versions gracefully if needed.

## Changelog

### v1 (Current)

- Job listing with pagination
- Job status tracking
- User settings management
- Glassdoor rating integration
- Multi-source job aggregation

Future versions may include:

- Job salary history
- Company interview insights
- Saved searches
- Bulk operations
- Export/reporting

## Support

For API issues, check:

1. Cognito token validity (refresh if expired)
2. CORS headers from API
3. Network tab in DevTools
4. API server logs (if accessible)
5. AWS CloudWatch logs for Lambda/API Gateway
