import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { JobFilters } from '@/types';
import { useJobs } from '@/hooks/useJobs';
import { FilterBar } from '@/components/FilterBar';
import { JobList } from '@/components/JobList';
import { formatDistanceToNow } from 'date-fns';
import { RefreshCw } from 'lucide-react';

export function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Parse filters from URL
  const filters: JobFilters = useMemo(() => {
    return {
      dateRange: (searchParams.get('dateRange') as any) || undefined,
      minRating: searchParams.get('minRating') ? parseFloat(searchParams.get('minRating')!) : undefined,
      status: (searchParams.get('status') as any) || undefined,
      search: searchParams.get('search') || undefined,
      sort: (searchParams.get('sort') as any) || 'date',
    };
  }, [searchParams]);

  // Sync filters to URL
  const updateFilters = (newFilters: JobFilters) => {
    const params = new URLSearchParams();
    if (newFilters.dateRange) params.set('dateRange', newFilters.dateRange);
    if (newFilters.minRating) params.set('minRating', String(newFilters.minRating));
    if (newFilters.status) params.set('status', newFilters.status);
    if (newFilters.search) params.set('search', newFilters.search);
    if (newFilters.sort) params.set('sort', newFilters.sort);
    setSearchParams(params);
    setCurrentPage(1); // Reset to page 1 when filters change
  };

  const { data, isLoading, error, refetch } = useJobs(filters, currentPage, pageSize);

  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
              Job Postings
              {data && (
                <span className="text-lg font-normal text-gray-600">
                  ({data.totalCount})
                </span>
              )}
            </h1>
            {data && (
              <p className="text-sm text-gray-600 mt-1">
                Last updated {formatDistanceToNow(new Date(data.items[0]?.createdAt || Date.now()), {
                  addSuffix: true,
                })}
              </p>
            )}
          </div>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-lg transition-colors self-start sm:self-auto"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      <FilterBar filters={filters} onFiltersChange={updateFilters} activeFilterCount={activeFilterCount} />

      {/* Job List */}
      <JobList
        data={data}
        isLoading={isLoading}
        error={error}
        onPageChange={setCurrentPage}
        onPageSizeChange={setPageSize}
        currentPage={currentPage}
        pageSize={pageSize}
      />
    </div>
  );
}
