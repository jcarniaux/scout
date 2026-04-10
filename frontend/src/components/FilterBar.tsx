import { useState } from 'react';
import { DateRange, JobFilters, ApplicationStatus } from '@/types';
import { X } from 'lucide-react';

interface FilterBarProps {
  filters: JobFilters;
  onFiltersChange: (filters: JobFilters) => void;
  activeFilterCount: number;
}

export function FilterBar({ filters, onFiltersChange, activeFilterCount }: FilterBarProps) {
  const [expanded, setExpanded] = useState(true);

  const updateFilter = (key: keyof JobFilters, value: any) => {
    onFiltersChange({ ...filters, [key]: value });
  };

  const clearFilters = () => {
    onFiltersChange({});
  };

  const dateRangeOptions: DateRange[] = ['24h', '7d', '30d'];
  const statusOptions: ApplicationStatus[] = [
    'NOT_APPLIED',
    'APPLIED',
    'RECRUITER_INTERVIEW',
    'TECHNICAL_INTERVIEW',
    'OFFER_RECEIVED',
    'OFFER_ACCEPTED',
  ];
  const sortOptions: Array<{ value: 'date' | 'salary' | 'rating'; label: string }> = [
    { value: 'date', label: 'Most Recent' },
    { value: 'salary', label: 'Highest Salary' },
    { value: 'rating', label: 'Best Rated' },
  ];

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">Filters</h3>
        <div className="flex items-center gap-2">
          {activeFilterCount > 0 && (
            <span className="px-2 py-1 bg-primary text-white text-xs font-medium rounded-full">
              {activeFilterCount}
            </span>
          )}
          {activeFilterCount > 0 && (
            <button
              onClick={clearFilters}
              className="px-3 py-1 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors flex items-center gap-1"
            >
              <X className="w-4 h-4" />
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="space-y-4">
        {/* Date Range */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Posted</label>
          <div className="flex flex-wrap gap-2">
            {dateRangeOptions.map((range) => (
              <button
                key={range}
                onClick={() => updateFilter('dateRange', filters.dateRange === range ? undefined : range)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                  filters.dateRange === range
                    ? 'bg-primary text-white'
                    : 'bg-slate-100 text-gray-700 hover:bg-slate-200'
                }`}
              >
                {range === '24h' ? 'Last 24h' : range === '7d' ? 'Last 7 Days' : 'Last 30 Days'}
              </button>
            ))}
          </div>
        </div>

        {/* Rating Range */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Min Glassdoor Rating: {filters.minRating?.toFixed(1) || 'Any'}
          </label>
          <input
            type="range"
            min="1"
            max="5"
            step="0.5"
            value={filters.minRating || 1}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              updateFilter('minRating', val === 1 ? undefined : val);
            }}
            className="w-full"
          />
        </div>

        {/* Status */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Application Status</label>
          <select
            value={filters.status || 'all'}
            onChange={(e) =>
              updateFilter(
                'status',
                e.target.value === 'all' ? undefined : (e.target.value as ApplicationStatus)
              )
            }
            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1"
          >
            <option value="all">All</option>
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {status === 'NOT_APPLIED'
                  ? 'Not Applied'
                  : status === 'APPLIED'
                    ? 'Applied'
                    : status === 'RECRUITER_INTERVIEW'
                      ? 'Recruiter Interview'
                      : status === 'TECHNICAL_INTERVIEW'
                        ? 'Technical Interview'
                        : status === 'OFFER_RECEIVED'
                          ? 'Offer Received'
                          : 'Offer Accepted'}
              </option>
            ))}
          </select>
        </div>

        {/* Search */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Search</label>
          <input
            type="text"
            placeholder="Role, company, location..."
            value={filters.search || ''}
            onChange={(e) => updateFilter('search', e.target.value || undefined)}
            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1"
          />
        </div>

        {/* Sort */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Sort By</label>
          <select
            value={filters.sort || 'date'}
            onChange={(e) => updateFilter('sort', e.target.value as 'date' | 'salary' | 'rating')}
            className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1"
          >
            {sortOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
