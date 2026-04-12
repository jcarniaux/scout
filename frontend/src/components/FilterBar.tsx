import { DateRange, JobFilters, JobSource, ApplicationStatus } from '@/types';
import { X } from 'lucide-react';

interface FilterBarProps {
  filters: JobFilters;
  onFiltersChange: (filters: JobFilters) => void;
  activeFilterCount: number;
}

const STATUS_LABELS: Record<ApplicationStatus, string> = {
  NOT_APPLIED:         'Not Applied',
  NOT_INTERESTED:      'Not Interested',
  APPLIED:             'Applied',
  RECRUITER_INTERVIEW: 'Recruiter Interview',
  TECHNICAL_INTERVIEW: 'Technical Interview',
  OFFER_RECEIVED:      'Offer Received',
  OFFER_ACCEPTED:      'Offer Accepted',
};

const statusOptions = Object.keys(STATUS_LABELS) as ApplicationStatus[];

export function FilterBar({ filters, onFiltersChange, activeFilterCount }: FilterBarProps) {
  const updateFilter = (key: keyof JobFilters, value: JobFilters[keyof JobFilters]) => {
    onFiltersChange({ ...filters, [key]: value });
  };

  const clearFilters = () => onFiltersChange({});

  const dateRangeOptions: DateRange[] = ['24h', '7d', '30d'];
  const sourceOptions: Array<{ value: JobSource; label: string }> = [
    { value: 'linkedin',  label: 'LinkedIn' },
    { value: 'indeed',    label: 'Indeed'   },
    { value: 'dice',      label: 'Dice'     },
  ];
  const sortOptions: Array<{ value: 'date' | 'salary' | 'rating'; label: string }> = [
    { value: 'date',   label: 'Most Recent' },
    { value: 'salary', label: 'Highest Salary' },
    { value: 'rating', label: 'Best Rated' },
  ];

  const inputClass =
    'w-full px-3 py-2 border border-slate-200 dark:border-gray-600 rounded-lg text-sm font-medium ' +
    'bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 ' +
    'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 dark:focus:ring-offset-gray-900 ' +
    'transition-colors';

  const labelClass = 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2';

  return (
    <div className="bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900 dark:text-white">Filters</h3>
        <div className="flex items-center gap-2">
          {activeFilterCount > 0 && (
            <span className="px-2 py-1 bg-primary text-white text-xs font-medium rounded-full">
              {activeFilterCount}
            </span>
          )}
          {activeFilterCount > 0 && (
            <button
              onClick={clearFilters}
              className="px-3 py-1 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors flex items-center gap-1"
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
          <label className={labelClass}>Posted</label>
          <div className="flex flex-wrap gap-2">
            {dateRangeOptions.map((range) => (
              <button
                key={range}
                onClick={() => updateFilter('dateRange', filters.dateRange === range ? undefined : range)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                  filters.dateRange === range
                    ? 'bg-primary text-white'
                    : 'bg-slate-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-slate-200 dark:hover:bg-gray-600'
                }`}
              >
                {range === '24h' ? 'Last 24h' : range === '7d' ? 'Last 7 Days' : 'Last 30 Days'}
              </button>
            ))}
          </div>
        </div>

        {/* Source Platform */}
        <div>
          <label className={labelClass}>Source</label>
          <div className="flex flex-wrap gap-2">
            {sourceOptions.map(({ value, label }) => {
              const active = (filters.sources ?? []).includes(value);
              const toggle = () => {
                const current = filters.sources ?? [];
                const next = active
                  ? current.filter((s) => s !== value)
                  : [...current, value];
                onFiltersChange({ ...filters, sources: next.length ? next : undefined });
              };
              return (
                <button
                  key={value}
                  onClick={toggle}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                    active
                      ? 'bg-primary text-white'
                      : 'bg-slate-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-slate-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Rating Range */}
        <div>
          <label className={labelClass}>
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
            className="w-full accent-primary"
          />
        </div>

        {/* Status */}
        <div>
          <label className={labelClass}>Application Status</label>
          <select
            value={filters.status || 'all'}
            onChange={(e) =>
              updateFilter('status', e.target.value === 'all' ? undefined : (e.target.value as ApplicationStatus))
            }
            className={inputClass}
          >
            <option value="all">All</option>
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </div>

        {/* Search */}
        <div>
          <label className={labelClass}>Search</label>
          <input
            type="text"
            placeholder="Role, company, location..."
            value={filters.search || ''}
            onChange={(e) => updateFilter('search', e.target.value || undefined)}
            className={inputClass.replace('font-medium', '')}
          />
        </div>

        {/* Sort */}
        <div>
          <label className={labelClass}>Sort By</label>
          <select
            value={filters.sort || 'date'}
            onChange={(e) => updateFilter('sort', e.target.value as 'date' | 'salary' | 'rating')}
            className={inputClass}
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
