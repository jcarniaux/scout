import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { Job, JobFilters, PaginatedResponse, UserSettings, ApplicationStatus } from '@/types';

const JOBS_QUERY_KEY = 'jobs';
const SETTINGS_QUERY_KEY = 'settings';

export function useJobs(filters: JobFilters, page: number = 1, pageSize: number = 20) {
  return useQuery<PaginatedResponse<Job>, Error>({
    queryKey: [JOBS_QUERY_KEY, filters, page, pageSize],
    queryFn: () => api.getJobs(filters, page, pageSize),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useJob(jobId: string) {
  return useQuery<Job, Error>({
    queryKey: [JOBS_QUERY_KEY, jobId],
    queryFn: () => api.getJob(jobId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ jobId, status, notes }: { jobId: string; status: ApplicationStatus; notes?: string }) =>
      api.updateStatus(jobId, status, notes),
    onSuccess: () => {
      // Invalidate all job-related queries
      queryClient.invalidateQueries({ queryKey: [JOBS_QUERY_KEY] });
    },
  });
}

export function useSettings() {
  return useQuery<UserSettings, Error>({
    queryKey: [SETTINGS_QUERY_KEY],
    queryFn: () => api.getSettings(),
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (settings: UserSettings) => api.updateSettings(settings),
    onSuccess: (data) => {
      queryClient.setQueryData([SETTINGS_QUERY_KEY], data);
    },
  });
}

/**
 * Synchronously score a single job against the user's resume.
 * Returns { score, reasoning } directly — no polling required.
 */
export function useScoreJob() {
  return useMutation({
    mutationFn: (jobId: string) => api.scoreJob(jobId),
  });
}
