import { ApplicationStatus } from '@/types';

interface StatusBadgeProps {
  status: ApplicationStatus | undefined;
}

const statusConfig: Record<ApplicationStatus, { classes: string; label: string }> = {
  NOT_APPLIED:         { classes: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',        label: 'Not Applied' },
  NOT_INTERESTED:      { classes: 'bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-300',            label: 'Not Interested' },
  APPLIED:             { classes: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',            label: 'Applied' },
  RECRUITER_INTERVIEW: { classes: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',        label: 'Recruiter Interview' },
  TECHNICAL_INTERVIEW: { classes: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',    label: 'Technical Interview' },
  OFFER_RECEIVED:      { classes: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300', label: 'Offer Received' },
  OFFER_ACCEPTED:      { classes: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',        label: 'Offer Accepted' },
};

export function StatusBadge({ status }: StatusBadgeProps) {
  if (!status) return null;
  const { classes, label } = statusConfig[status];
  return (
    <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${classes}`}>
      {label}
    </span>
  );
}
