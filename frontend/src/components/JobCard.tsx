import { formatDistanceToNow } from 'date-fns';
import { Job, ApplicationStatus } from '@/types';
import { StatusSelect } from './StatusSelect';
import { RatingBadge } from './RatingBadge';
import { ExternalLink, MapPin, DollarSign, Calendar } from 'lucide-react';
import { useUpdateStatus } from '@/hooks/useJobs';

function formatPostedDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Date unknown';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return 'Date unknown';
  return formatDistanceToNow(date, { addSuffix: true });
}

interface JobCardProps {
  job: Job;
}

const sourceColors: Record<string, string> = {
  linkedin:      'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  indeed:        'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
  glassdoor:     'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  ziprecruiter:  'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
  dice:          'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
};

export function JobCard({ job }: JobCardProps) {
  const updateStatus = useUpdateStatus();

  const handleStatusChange = (status: ApplicationStatus) => {
    updateStatus.mutate({ jobId: job.jobId, status });
  };

  const salaryDisplay =
    job.salaryMin && job.salaryMax
      ? `$${(job.salaryMin / 1000).toFixed(0)}K – $${(job.salaryMax / 1000).toFixed(0)}K`
      : null;

  const sourceLabel = job.source.charAt(0).toUpperCase() + job.source.slice(1);
  const sourceClass = sourceColors[job.source] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-slate-200 dark:border-gray-700 px-5 py-4 hover:shadow-md dark:hover:shadow-gray-900 transition-shadow">

      {/* Row 1 — role title + status select */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 mb-1.5">
        <h3 className="text-base font-semibold text-gray-900 dark:text-white leading-snug">
          {job.roleName}
        </h3>
        <div className="shrink-0">
          <StatusSelect
            value={job.applicationStatus}
            onChange={handleStatusChange}
            disabled={updateStatus.isPending}
          />
        </div>
      </div>

      {/* Row 2 — company · rating · source · location · date · salary · View Posting */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm mb-2">
        <span className="font-medium text-gray-700 dark:text-gray-200">{job.company}</span>
        <RatingBadge rating={job.glassdoorRating} glassdoorUrl={job.glassdoorUrl} />
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${sourceClass}`}>
          {sourceLabel}
        </span>
        <span className="text-gray-300 dark:text-gray-600">·</span>
        <span className="flex items-center gap-1 text-gray-500 dark:text-gray-400">
          <MapPin className="w-3.5 h-3.5 shrink-0" />
          {job.location || 'Location unknown'}
        </span>
        <span className="text-gray-300 dark:text-gray-600">·</span>
        <span className="flex items-center gap-1 text-gray-500 dark:text-gray-400">
          <Calendar className="w-3.5 h-3.5 shrink-0" />
          {formatPostedDate(job.postedDate)}
        </span>
        {salaryDisplay && (
          <>
            <span className="text-gray-300 dark:text-gray-600">·</span>
            <span className="flex items-center gap-1 text-green-600 dark:text-green-400 font-medium">
              <DollarSign className="w-3.5 h-3.5 shrink-0" />
              {salaryDisplay}
            </span>
          </>
        )}
        <span className="text-gray-300 dark:text-gray-600">·</span>
        <a
          href={job.sourceUrl ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-primary hover:text-primary-700 dark:text-blue-400 dark:hover:text-blue-300 font-medium transition-colors"
        >
          View Posting
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>

      {/* Row 4 — benefits pills (optional) */}
      {(job.ptoDays || job.sickDays || job.match401k || job.benefits) && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {job.ptoDays && (
            <span className="px-2 py-0.5 bg-slate-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300 text-xs font-medium rounded-full">
              {job.ptoDays} PTO days
            </span>
          )}
          {job.sickDays && (
            <span className="px-2 py-0.5 bg-slate-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300 text-xs font-medium rounded-full">
              {job.sickDays} sick days
            </span>
          )}
          {job.match401k && (
            <span className="px-2 py-0.5 bg-slate-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300 text-xs font-medium rounded-full">
              {job.match401k} 401(k)
            </span>
          )}
          {job.benefits && (
            <span className="px-2 py-0.5 bg-slate-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300 text-xs font-medium rounded-full truncate max-w-xs">
              {job.benefits}
            </span>
          )}
        </div>
      )}

      {/* Notes (optional) */}
      {job.notes && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3 line-clamp-2">{job.notes}</p>
      )}

    </div>
  );
}
