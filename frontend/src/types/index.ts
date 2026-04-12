export interface Job {
  jobId: string;
  roleName: string | null;
  company: string;
  location: string;
  salaryMin: number | null;
  salaryMax: number | null;
  ptoDays: number | null;
  sickDays: number | null;
  match401k: string | null;
  benefits: string | null;
  postedDate: string | null;
  sourceUrl: string | null;
  source: string;
  glassdoorRating: number | null;
  glassdoorUrl: string | null;
  createdAt: string | null;
  description: string | null;
  jobType: string | null;
  applicationStatus: ApplicationStatus;
  notes: string | null;
}

export type ApplicationStatus =
  | 'NOT_APPLIED'
  | 'NOT_INTERESTED'
  | 'APPLIED'
  | 'RECRUITER_INTERVIEW'
  | 'TECHNICAL_INTERVIEW'
  | 'OFFER_RECEIVED'
  | 'OFFER_ACCEPTED';

export type DateRange = '24h' | '7d' | '30d';

export type JobSource = 'linkedin' | 'indeed' | 'dice' | 'glassdoor' | 'ziprecruiter';

export interface JobFilters {
  dateRange?: DateRange;
  status?: ApplicationStatus;
  search?: string;
  sort?: 'date' | 'salary' | 'rating';
  sources?: string[];
}

export interface SearchLocation {
  location: string;
  distance: number | null;
  remote: boolean;
}

export interface SearchPreferences {
  roleQueries: string[];
  locations: SearchLocation[];
  salaryMin: number | null;
  salaryMax: number | null;
}

export interface UserSettings {
  email: string;
  dailyReport: boolean;
  weeklyReport: boolean;
  searchPreferences: SearchPreferences;
}

export interface PaginatedResponse<T> {
  items: T[];
  totalCount: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}
