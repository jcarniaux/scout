import { DateRange, JobFilters, JobSource, ApplicationStatus, ContractType } from '@/types';
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
  const dateRangeLabels: Record<DateRange, string> = { '24h': '24h', '7d': '7d', '30d': '30d' };

  const sourceOptions: Array<{ value: JobSource; label: string }> = [
    { value: 'linkedin',     label: 'LinkedIn'     },
    { value: 'indeed',       label: 'Indeed'       },
    { value: 'dice',         label: 'Dice'         },
    { value: 'glassdoor',    label: 'Glassdoor'    },
    { value: 'ziprecruiter', label: 'ZipRecruiter' },
  ];

  const contractTypeOptions: Array<{ value: ContractType; label: string }> = [
    { value: 'permanent', label: 'Permanent' },
    { value: 'contract',  label: 'Contract'  },
    { value: 'freelance', label: 'Freelance' },
  ];

  const sortOptions: Array<{ value: 'date' | 'salary' | 'rating' | 'match'; label: string }> = [
    { value: 'date',   label: 'Most Recent'    },
    { value: 'salary', label: 'Highest Salary' },
    { value: 'rating', label: 'Best Rated'     },
    { value: 'match',  label: 'Best Match ✦'   },
  ];

  const pillClass = (active: boolean) =>
    `px-3 py-1 rounded-full text-xs font-medium transition-colors ${
      active
        ? 'bg-primary text-white'
        : 'bg-slate-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-slate-200 dark:hover:bg-gray-600'
    }`;

  const selectClass =
    'w-full px-2 py-1.5 border border-slate-200 dark:border-gray-600 rounded-lg text-sm ' +
    'bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 ' +
    'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 dark:focus:ring-offset-gray-900 ' +
    'transition-colors';

  const labelClass = 'block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5';

  return (
    <div className="bg-white dark:bg-gray-800 border border-slate-200 dark:border-gray-700 rounded-lg p-3 mb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Filters</h3>
        {activeFilterCount > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="px-1.5 py-0.5 bg-primary text-white text-xs font-medium rounded-full">
              {activeFilterCount}
            </span>
            <button
              onClick={clearFilters}
              className="px-2 py-0.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors flex items-center gap-1"
            >
              <X className="w-3 h-3" />
              Clear
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Search — spans both columns */}
        <div className="sm:col-span-2">
          <label className={labelClass}>Search</label>
          <input
            type="text"
            placeholder="Role, company, location..."
            value={filters.search || ''}
            onChange={(e) => updateFilter('search', e.target.value || undefined)}
            className={selectClass}
          />
        </div>

        {/* Posted */}
        <div>
          <label className={labelClass}>Posted</label>
          <div className="flex gap-1.5">
            {dateRangeOptions.map((range) => (
              <button
                key={range}
                onClick={() => updateFilter('dateRange', filters.dateRange === range ? undefined : range)}
                className={pillClass(filters.dateRange === range)}
              >
                {dateRangeLabels[range]}
              </button>
            ))}
          </div>
        </div>

        {/* Source */}
        <div>
          <label className={labelClass}>Source</label>
          <div className="flex gap-1.5">
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
                <button key={value} onClick={toggle} className={pillClass(active)}>
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Contract Type */}
        <div>
          <label className={labelClass}>Contract Type</label>
          <div className="flex gap-1.5">
            {contractTypeOptions.map(({ value, label }) => {
              const active = (filters.contractTypes ?? []).includes(value);
              const toggle = () => {
                const current = filters.contractTypes ?? [];
                const next = active
                  ? current.filter((t) => t !== value)
                  : [...current, value];
                onFiltersChange({ ...filters, contractTypes: next.length ? next : undefined });
              };
              return (
                <button key={value} onClick={toggle} className={pillClass(active)}>
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Status */}
        <div>
          <label className={labelClass}>Status</label>
          <select
            value={filters.status || 'all'}
            onChange={(e) =>
              updateFilter('status', e.target.value === 'all' ? undefined : (e.target.value as ApplicationStatus))
            }
            className={selectClass}
          >
            <option value="all">All statuses</option>
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </div>

        {/* Sort */}
        <div>
          <label className={labelClass}>Sort By</label>
          <select
            value={filters.sort || 'date'}
            onChange={(e) => updateFilter('sort', e.target.value as 'date' | 'salary' | 'rating' | 'match')}
            className={selectClass}
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
