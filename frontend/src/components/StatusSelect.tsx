import { ApplicationStatus } from '@/types';

interface StatusSelectProps {
  value: ApplicationStatus | undefined;
  onChange: (status: ApplicationStatus) => void;
  disabled?: boolean;
}

const statusOptions: Array<{ value: ApplicationStatus; label: string }> = [
  { value: 'NOT_APPLIED',   label: 'Not Applied' },
  { value: 'NOT_INTERESTED', label: 'Not Interested' },
  { value: 'APPLIED',       label: 'Applied' },
  { value: 'RECRUITER_INTERVIEW', label: 'Recruiter Interview' },
  { value: 'TECHNICAL_INTERVIEW', label: 'Technical Interview' },
  { value: 'OFFER_RECEIVED', label: 'Offer Received' },
  { value: 'OFFER_ACCEPTED', label: 'Offer Accepted' },
];

const statusBorderMap: Record<ApplicationStatus, string> = {
  NOT_APPLIED:         'border-slate-300 dark:border-gray-600',
  NOT_INTERESTED:      'border-rose-300 dark:border-rose-700',
  APPLIED:             'border-blue-300 dark:border-blue-700',
  RECRUITER_INTERVIEW: 'border-amber-300 dark:border-amber-700',
  TECHNICAL_INTERVIEW: 'border-orange-300 dark:border-orange-700',
  OFFER_RECEIVED:      'border-emerald-300 dark:border-emerald-700',
  OFFER_ACCEPTED:      'border-green-300 dark:border-green-700',
};

export function StatusSelect({ value, onChange, disabled = false }: StatusSelectProps) {
  const borderClass = value ? statusBorderMap[value] : 'border-slate-300 dark:border-gray-600';

  return (
    <select
      value={value || 'NOT_APPLIED'}
      onChange={(e) => onChange(e.target.value as ApplicationStatus)}
      disabled={disabled}
      className={`px-3 py-1.5 rounded-md text-sm font-medium border-2 ${borderClass}
        bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200
        hover:bg-gray-50 dark:hover:bg-gray-700
        disabled:opacity-50 disabled:cursor-not-allowed
        focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1
        dark:focus:ring-offset-gray-800 transition-colors`}
    >
      {statusOptions.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
