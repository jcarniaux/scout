import { Star } from 'lucide-react';

interface RatingBadgeProps {
  rating: number | null | undefined;
  glassdoorUrl?: string | null;
}

function getRatingColor(rating: number | null | undefined): string {
  if (rating === null || rating === undefined) return 'text-gray-400';
  if (rating >= 4.0) return 'text-green-600';
  if (rating >= 3.0) return 'text-yellow-600';
  return 'text-red-600';
}

function getRatingBgColor(rating: number | null | undefined): string {
  if (rating === null || rating === undefined) return 'bg-gray-50';
  if (rating >= 4.0) return 'bg-green-50';
  if (rating >= 3.0) return 'bg-yellow-50';
  return 'bg-red-50';
}

export function RatingBadge({ rating, glassdoorUrl }: RatingBadgeProps) {
  const content = (
    <div className={`flex items-center gap-1 px-2 py-1 rounded-full text-sm font-medium ${getRatingBgColor(rating)}`}>
      <Star className={`w-3 h-3 fill-current ${getRatingColor(rating)}`} />
      <span className={getRatingColor(rating)}>
        {rating !== null && rating !== undefined ? rating.toFixed(1) : 'N/A'}
      </span>
    </div>
  );

  if (glassdoorUrl && rating !== null && rating !== undefined) {
    return (
      <a href={glassdoorUrl} target="_blank" rel="noopener noreferrer" className="hover:opacity-75">
        {content}
      </a>
    );
  }

  return content;
}
