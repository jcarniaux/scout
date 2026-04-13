import { fetchAuthSession } from 'aws-amplify/auth';
import { Job, JobFilters, PaginatedResponse, UserSettings, SearchLocation, ApplicationStatus, ResumeStatus } from '@/types';

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
  getJobs: async (filters: JobFilters, page = 1, pageSize = 20): Promise<PaginatedResponse<Job>> => {
    const params = new URLSearchParams();
    if (filters.dateRange)           params.set('dateRange', filters.dateRange);
    if (filters.status)              params.set('status', filters.status);
    if (filters.search)              params.set('search', filters.search);
    if (filters.sort)                params.set('sort', filters.sort);
    if (filters.sources?.length)     params.set('sources', filters.sources.join(','));
    params.set('page', String(page));
    params.set('pageSize', String(pageSize));
    // API returns {jobs, total, page, pageSize, hasMore} — map to PaginatedResponse shape
    const raw = await authFetch(`/jobs?${params}`);
    return {
      items: raw.jobs ?? [],
      totalCount: raw.total ?? 0,
      page: raw.page ?? page,
      pageSize: raw.pageSize ?? pageSize,
      hasMore: raw.hasMore ?? false,
    };
  },

  getJob: (jobId: string): Promise<Job> => authFetch(`/jobs/${jobId}`),

  updateStatus: (jobId: string, status: ApplicationStatus, notes?: string) =>
    authFetch(`/jobs/${jobId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, notes }),
    }),

  getSettings: async (): Promise<UserSettings> => {
    const raw = await authFetch('/user/settings');
    const sp = raw.search_preferences ?? {};
    return {
      email: raw.email ?? '',
      dailyReport: raw.daily_report ?? false,
      weeklyReport: raw.weekly_report ?? false,
      searchPreferences: {
        roleQueries: sp.role_queries ?? [],
        locations: (sp.locations ?? []).map((l: Partial<SearchLocation>) => ({
          location: l.location ?? '',
          distance: l.distance ?? null,
          remote: l.remote ?? false,
        })),
        salaryMin: sp.salary_min ?? null,
        salaryMax: sp.salary_max ?? null,
      },
      resumeStatus: (raw.resume_status ?? null) as ResumeStatus,
      resumeFilename: raw.resume_filename ?? null,
    };
  },

  updateSettings: async (settings: UserSettings): Promise<UserSettings> => {
    const body = {
      email: settings.email,
      daily_report: settings.dailyReport,
      weekly_report: settings.weeklyReport,
      search_preferences: {
        role_queries: settings.searchPreferences.roleQueries,
        locations: settings.searchPreferences.locations.map((l) => ({
          location: l.location,
          distance: l.distance,
          remote: l.remote,
        })),
        salary_min: settings.searchPreferences.salaryMin,
        salary_max: settings.searchPreferences.salaryMax,
      },
    };
    const raw = await authFetch('/user/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    });
    const sp = raw.search_preferences ?? {};
    return {
      email: raw.email ?? settings.email,
      dailyReport: raw.daily_report ?? settings.dailyReport,
      weeklyReport: raw.weekly_report ?? settings.weeklyReport,
      searchPreferences: {
        roleQueries: sp.role_queries ?? [],
        locations: (sp.locations ?? []).map((l: Partial<SearchLocation>) => ({
          location: l.location ?? '',
          distance: l.distance ?? null,
          remote: l.remote ?? false,
        })),
        salaryMin: sp.salary_min ?? null,
        salaryMax: sp.salary_max ?? null,
      },
      resumeStatus: settings.resumeStatus,
      resumeFilename: settings.resumeFilename,
    };
  },

  /**
   * Request a short-lived S3 pre-signed PUT URL for uploading a resume PDF.
   * The upload itself is done directly from the browser to S3 (not through the API).
   */
  getResumeUploadUrl: async (): Promise<{ uploadUrl: string; s3Key: string; expiresIn: number }> => {
    return authFetch('/user/resume/upload-url', { method: 'POST' });
  },

  /**
   * Upload a PDF file directly to S3 using the pre-signed URL.
   * Returns when the upload is complete.
   */
  uploadResumeTos3: async (uploadUrl: string, file: File): Promise<void> => {
    const response = await fetch(uploadUrl, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/pdf' },
      body: file,
    });
    if (!response.ok) {
      throw new Error(`S3 upload failed: ${response.status}`);
    }
  },

  /** Delete the user's resume from S3 and clear DynamoDB resume fields. */
  deleteResume: async (): Promise<void> => {
    await authFetch('/user/resume', { method: 'DELETE' });
  },
};
