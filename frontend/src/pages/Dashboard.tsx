import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { JobFilters, JobSource, DateRange, ApplicationStatus } from '@/types';
import { useJobs } from '@/hooks/useJobs';
import { FilterBar } from '@/components/FilterBar';
import { JobList } from '@/components/JobList';
import { formatDistanceToNow } from 'date-fns';
import { RefreshCw } from 'lucide-react';

export function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const filters: JobFilters = useMemo(() => {
    const rawSources = searchParams.get('sources');
    const sources = rawSources
      ? (rawSources.split(',').filter(Boolean) as JobSource[])
      : undefined;
    return {
      dateRange:  (searchParams.get('dateRange') as DateRange) || undefined,
      minRating:  searchParams.get('minRating') ? parseFloat(searchParams.get('minRating')!) : undefined,
      status:     (searchParams.get('status') as ApplicationStatus) || undefined,
      search:     searchParams.get('search') || undefined,
      sort:       (searchParams.get('sort') as JobFilters['sort']) || 'date',
      sources,
    };
  }, [searchParams]);

  const updateFilters = (newFilters: JobFilters) => {
    const params = new URLSearchParams();
    if (newFilters.dateRange)                params.set('dateRange', newFilters.dateRange);
    if (newFilters.minRating)                params.set('minRating', String(newFilters.minRating));
    if (newFilters.status)                   params.set('status', newFilters.status);
    if (newFilters.search)                   params.set('search', newFilters.search);
    if (newFilters.sort)                     params.set('sort', newFilters.sort);
    if (newFilters.sources?.length)          params.set('sources', newFilters.sources.join(','));
    setSearchParams(params);
    setCurrentPage(1);
  };

  const { data, isLoading, error, refetch } = useJobs(filters, currentPage, pageSize);
  const activeFilterCount = Object.entries(filters).filter(([, v]) =>
    v !== undefined && v !== 'date' && !(Array.isArray(v) && v.length === 0)
  ).length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              Job Postings
              {data && (
                <span className="text-lg font-normal text-gray-500 dark:text-gray-400">
                  ({data.totalCount})
                </span>
              )}
            </h1>
            {data && data.items.length > 0 && (() => {
              const d = new Date(data.items[0].createdAt);
              return !isNaN(d.getTime()) ? (
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  Last updated {formatDistanceToNow(d, { addSuffix: true })}
                </p>
              ) : null;
            })()}
          </div>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 font-medium rounded-lg transition-colors self-start sm:self-auto"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      <FilterBar filters={filters} onFiltersChange={updateFilters} activeFilterCount={activeFilterCount} />
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
