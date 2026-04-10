import { fetchAuthSession } from 'aws-amplify/auth';
import { Job, JobFilters, PaginatedResponse, UserSettings, ApplicationStatus } from '@/types';

const API_URL = import.meta.env.VITE_API_URL;

async function authFetch(path: string, options: RequestInit = {}) {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: token || '',
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  return response.json();
}

export const api = {
  getJobs: (filters: JobFilters, page = 1, pageSize = 20): Promise<PaginatedResponse<Job>> => {
    const params = new URLSearchParams();
    if (filters.dateRange) params.set('dateRange', filters.dateRange);
    if (filters.minRating) params.set('minRating', String(filters.minRating));
    if (filters.status) params.set('status', filters.status);
    if (filters.search) params.set('search', filters.search);
    if (filters.sort) params.set('sort', filters.sort);
    params.set('page', String(page));
    params.set('pageSize', String(pageSize));
    return authFetch(`/jobs?${params}`);
  },

  getJob: (jobId: string): Promise<Job> => authFetch(`/jobs/${jobId}`),

  updateStatus: (jobId: string, status: ApplicationStatus, notes?: string) =>
    authFetch(`/jobs/${jobId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, notes }),
    }),

  getSettings: (): Promise<UserSettings> => authFetch('/user/settings'),

  updateSettings: (settings: UserSettings): Promise<UserSettings> =>
    authFetch('/user/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),
};
