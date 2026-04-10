export interface Job {
  jobId: string;
  roleName: string;
  company: string;
  location: string;
  salaryMin: number | null;
  salaryMax: number | null;
  ptoDays: number | null;
  sickDays: number | null;
  match401k: string | null;
  benefits: string | null;
  postedDate: string;
  sourceUrl: string;
  source: 'linkedin' | 'indeed' | 'glassdoor' | 'ziprecruiter' | 'dice';
  glassdoorRating: number | null;
  glassdoorUrl: string | null;
  createdAt: string;
  applicationStatus?: ApplicationStatus;
  notes?: string;
}

export type ApplicationStatus =
  | 'NOT_APPLIED'
  | 'APPLIED'
  | 'RECRUITER_INTERVIEW'
  | 'TECHNICAL_INTERVIEW'
  | 'OFFER_RECEIVED'
  | 'OFFER_ACCEPTED';

export type DateRange = '24h' | '7d' | '30d';

export interface JobFilters {
  dateRange?: DateRange;
  minRating?: number;
  status?: ApplicationStatus;
  search?: string;
  sort?: 'date' | 'salary' | 'rating';
}

export interface UserSettings {
  email: string;
  dailyReport: boolean;
  weeklyReport: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  totalCount: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}
