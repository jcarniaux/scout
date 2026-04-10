import { ApplicationStatus } from '@/types';

interface StatusBadgeProps {
  status: ApplicationStatus | undefined;
}

const statusConfig: Record<ApplicationStatus, { bg: string; text: string; label: string }> = {
  NOT_APPLIED: { bg: 'bg-slate-100', text: 'text-slate-700', label: 'Not Applied' },
  APPLIED: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Applied' },
  RECRUITER_INTERVIEW: { bg: 'bg-amber-100', text: 'text-amber-700', label: 'Recruiter Interview' },
  TECHNICAL_INTERVIEW: { bg: 'bg-orange-100', text: 'text-orange-700', label: 'Technical Interview' },
  OFFER_RECEIVED: { bg: 'bg-emerald-100', text: 'text-emerald-700', label: 'Offer Received' },
  OFFER_ACCEPTED: { bg: 'bg-green-100', text: 'text-green-700', label: 'Offer Accepted' },
};

export function StatusBadge({ status }: StatusBadgeProps) {
  if (!status) return null;
  const config = statusConfig[status];
  return (
    <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}
