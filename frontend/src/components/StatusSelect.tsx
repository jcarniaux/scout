import { ApplicationStatus } from '@/types';

interface StatusSelectProps {
  value: ApplicationStatus | undefined;
  onChange: (status: ApplicationStatus) => void;
  disabled?: boolean;
}

const statusOptions: Array<{ value: ApplicationStatus; label: string }> = [
  { value: 'NOT_APPLIED', label: 'Not Applied' },
  { value: 'APPLIED', label: 'Applied' },
  { value: 'RECRUITER_INTERVIEW', label: 'Recruiter Interview' },
  { value: 'TECHNICAL_INTERVIEW', label: 'Technical Interview' },
  { value: 'OFFER_RECEIVED', label: 'Offer Received' },
  { value: 'OFFER_ACCEPTED', label: 'Offer Accepted' },
];

const statusColorMap: Record<ApplicationStatus, string> = {
  NOT_APPLIED: 'border-slate-200',
  APPLIED: 'border-blue-200',
  RECRUITER_INTERVIEW: 'border-amber-200',
  TECHNICAL_INTERVIEW: 'border-orange-200',
  OFFER_RECEIVED: 'border-emerald-200',
  OFFER_ACCEPTED: 'border-green-200',
};

export function StatusSelect({ value, onChange, disabled = false }: StatusSelectProps) {
  return (
    <select
      value={value || 'NOT_APPLIED'}
      onChange={(e) => onChange(e.target.value as ApplicationStatus)}
      disabled={disabled}
      className={`px-3 py-1.5 rounded-md text-sm font-medium border ${
        value ? statusColorMap[value] : 'border-slate-200'
      } bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1`}
    >
      {statusOptions.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
