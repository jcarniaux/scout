import { formatDistanceToNow } from 'date-fns';
import { Job, ApplicationStatus } from '@/types';
import { StatusSelect } from './StatusSelect';
import { RatingBadge } from './RatingBadge';
import { ExternalLink, MapPin, DollarSign, Calendar } from 'lucide-react';
import { useUpdateStatus } from '@/hooks/useJobs';

interface JobCardProps {
  job: Job;
}

const sourceColors: Record<string, string> = {
  linkedin: 'bg-blue-100 text-blue-700',
  indeed: 'bg-purple-100 text-purple-700',
  glassdoor: 'bg-green-100 text-green-700',
  ziprecruiter: 'bg-orange-100 text-orange-700',
  dice: 'bg-red-100 text-red-700',
};

export function JobCard({ job }: JobCardProps) {
  const updateStatus = useUpdateStatus();

  const handleStatusChange = (status: ApplicationStatus) => {
    updateStatus.mutate({ jobId: job.jobId, status });
  };

  const salaryDisplay =
    job.salaryMin && job.salaryMax
      ? `$${(job.salaryMin / 1000).toFixed(0)}K - $${(job.salaryMax / 1000).toFixed(0)}K`
      : 'Not disclosed';

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-5 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-3">
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-gray-900 mb-1">{job.roleName}</h3>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="font-medium text-gray-700">{job.company}</span>
            <RatingBadge rating={job.glassdoorRating} glassdoorUrl={job.glassdoorUrl} />
            <span
              className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${sourceColors[job.source] || 'bg-gray-100 text-gray-700'}`}
            >
              {job.source.charAt(0).toUpperCase() + job.source.slice(1)}
            </span>
          </div>
        </div>
        <StatusSelect
          value={job.applicationStatus}
          onChange={handleStatusChange}
          disabled={updateStatus.isPending}
        />
      </div>

      {/* Location and Date */}
      <div className="flex flex-wrap gap-4 text-sm text-gray-600 mb-4">
        <div className="flex items-center gap-1.5">
          <MapPin className="w-4 h-4 flex-shrink-0" />
          <span>{job.location}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Calendar className="w-4 h-4 flex-shrink-0" />
          <span>{formatDistanceToNow(new Date(job.postedDate), { addSuffix: true })}</span>
        </div>
      </div>

      {/* Salary */}
      <div className="flex items-center gap-1.5 mb-4 text-sm font-medium text-gray-900">
        <DollarSign className="w-4 h-4 flex-shrink-0 text-green-600" />
        <span>{salaryDisplay}</span>
      </div>

      {/* Benefits Row */}
      <div className="flex flex-wrap gap-2 mb-4">
        {job.ptoDays && (
          <span className="px-2.5 py-1 bg-slate-100 text-slate-700 text-xs font-medium rounded-full">
            {job.ptoDays} PTO days
          </span>
        )}
        {job.sickDays && (
          <span className="px-2.5 py-1 bg-slate-100 text-slate-700 text-xs font-medium rounded-full">
            {job.sickDays} Sick days
          </span>
        )}
        {job.match401k && (
          <span className="px-2.5 py-1 bg-slate-100 text-slate-700 text-xs font-medium rounded-full">
            {job.match401k} 401(k)
          </span>
        )}
        {job.benefits && (
          <span className="px-2.5 py-1 bg-slate-100 text-slate-700 text-xs font-medium rounded-full truncate">
            {job.benefits}
          </span>
        )}
      </div>

      {/* Notes */}
      {job.notes && <p className="text-sm text-gray-600 mb-4 line-clamp-2">{job.notes}</p>}

      {/* Actions */}
      <div className="flex gap-2">
        <a
          href={job.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white font-medium rounded-lg hover:bg-primary-700 transition-colors"
        >
          View Posting
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>
    </div>
  );
}
