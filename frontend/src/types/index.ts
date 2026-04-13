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
  contractType: ContractType | null;
  applicationStatus: ApplicationStatus;
  notes: string | null;
  /** AI match score 0–100, null when no resume has been uploaded */
  matchScore: number | null;
  /** One-sentence explanation from Bedrock */
  matchReasoning: string | null;
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

export type ContractType = 'permanent' | 'contract' | 'freelance';

export interface JobFilters {
  dateRange?: DateRange;
  status?: ApplicationStatus;
  search?: string;
  sort?: 'date' | 'salary' | 'rating' | 'match';
  sources?: string[];
  contractTypes?: ContractType[];
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

export type ResumeStatus = 'processing' | 'ready' | 'error' | 'deleted' | null;

export type ScoringStatus = 'scoring' | 'done' | null;

export interface UserSettings {
  email: string;
  dailyReport: boolean;
  weeklyReport: boolean;
  searchPreferences: SearchPreferences;
  /** null until a resume has been uploaded */
  resumeStatus: ResumeStatus;
  resumeFilename: string | null;
  /** null until the first scoring run completes */
  scoringStatus: ScoringStatus;
  /** ISO timestamp of the last completed scoring run */
  lastScoredAt: string | null;
  /** Number of jobs scored in the last run */
  lastScoredCount: number | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  totalCount: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}
