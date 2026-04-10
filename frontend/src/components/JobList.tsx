import { Job, PaginatedResponse } from '@/types';
import { JobCard } from './JobCard';
import { EmptyState } from './EmptyState';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface JobListProps {
  data?: PaginatedResponse<Job>;
  isLoading: boolean;
  error: Error | null;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  currentPage: number;
  pageSize: number;
}

function JobCardSkeleton() {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-5">
      <div className="animate-pulse">
        <div className="h-6 bg-slate-200 rounded w-2/3 mb-3" />
        <div className="h-4 bg-slate-200 rounded w-1/2 mb-4" />
        <div className="space-y-2 mb-4">
          <div className="h-4 bg-slate-200 rounded w-full" />
          <div className="h-4 bg-slate-200 rounded w-3/4" />
        </div>
        <div className="h-10 bg-slate-200 rounded w-1/3" />
      </div>
    </div>
  );
}

export function JobList({
  data,
  isLoading,
  error,
  onPageChange,
  onPageSizeChange,
  currentPage,
  pageSize,
}: JobListProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <JobCardSkeleton />
        <JobCardSkeleton />
        <JobCardSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <h3 className="font-semibold text-red-900 mb-1">Error loading jobs</h3>
        <p className="text-red-700 text-sm mb-4">{error.message}</p>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        title="No jobs found"
        description="Try adjusting your filters or check back later for new opportunities"
        action={{
          label: 'Clear Filters',
          onClick: () => window.location.href = '/',
        }}
      />
    );
  }

  return (
    <div>
      {/* Job List */}
      <div className="space-y-4 mb-6">
        {data.items.map((job) => (
          <JobCard key={job.jobId} job={job} />
        ))}
      </div>

      {/* Pagination */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white rounded-lg border border-slate-200 p-4">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">Items per page:</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(parseInt(e.target.value))}
            className="px-3 py-1 border border-slate-200 rounded-lg text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
          </select>
        </div>

        <div className="text-sm text-gray-600">
          Page <span className="font-semibold">{currentPage}</span> of{' '}
          <span className="font-semibold">{Math.ceil(data.totalCount / pageSize)}</span> (
          <span className="font-semibold">{data.totalCount}</span> total)
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className="p-2 rounded-lg border border-slate-200 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Previous page"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={!data.hasMore}
            className="p-2 rounded-lg border border-slate-200 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Next page"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
