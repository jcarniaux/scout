import { useState, useEffect, useRef } from 'react';
import { useSettings, useUpdateSettings } from '@/hooks/useJobs';
import { SearchLocation, ResumeStatus } from '@/types';
import { api } from '@/services/api';
import { Check, AlertCircle, Plus, X, MapPin, Upload, Trash2, FileText, Loader2 } from 'lucide-react';

const DEFAULT_SEARCH_PREFS = {
  roleQueries: [] as string[],
  locations: [] as SearchLocation[],
  salaryMin: null as number | null,
  salaryMax: null as number | null,
};

export function Settings() {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();

  const [dailyReport, setDailyReport] = useState(false);
  const [weeklyReport, setWeeklyReport] = useState(false);

  // Search preferences
  const [roleQueries, setRoleQueries] = useState<string[]>([]);
  const [newRole, setNewRole] = useState('');
  const [locations, setLocations] = useState<SearchLocation[]>([]);
  const [newLocation, setNewLocation] = useState('');
  const [newDistance, setNewDistance] = useState<number | null>(25);
  const [newRemote, setNewRemote] = useState(false);
  const [salaryMin, setSalaryMin] = useState<string>('');
  const [salaryMax, setSalaryMax] = useState<string>('');

  // Resume upload state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [resumeStatus, setResumeStatus] = useState<ResumeStatus>(null);
  const [resumeFilename, setResumeFilename] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    if (settings) {
      setDailyReport(settings.dailyReport);
      setWeeklyReport(settings.weeklyReport);
      const sp = settings.searchPreferences ?? DEFAULT_SEARCH_PREFS;
      setRoleQueries(sp.roleQueries ?? []);
      setLocations(sp.locations ?? []);
      setSalaryMin(sp.salaryMin ? String(sp.salaryMin) : '');
      setSalaryMax(sp.salaryMax ? String(sp.salaryMax) : '');
      setResumeStatus(settings.resumeStatus ?? null);
      setResumeFilename(settings.resumeFilename ?? null);
    }
  }, [settings]);

  const addRole = () => {
    const trimmed = newRole.trim();
    if (trimmed && !roleQueries.includes(trimmed)) {
      setRoleQueries([...roleQueries, trimmed]);
      setNewRole('');
    }
  };

  const removeRole = (index: number) => {
    setRoleQueries(roleQueries.filter((_, i) => i !== index));
  };

  const addLocation = () => {
    const trimmed = newLocation.trim();
    if (trimmed) {
      setLocations([...locations, {
        location: trimmed,
        distance: newRemote ? null : newDistance,
        remote: newRemote,
      }]);
      setNewLocation('');
      setNewDistance(25);
      setNewRemote(false);
    }
  };

  const removeLocation = (index: number) => {
    setLocations(locations.filter((_, i) => i !== index));
  };

  const handleResumeUpload = async (file: File) => {
    if (!file || file.type !== 'application/pdf') {
      setUploadError('Please select a PDF file.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('File must be under 10 MB.');
      return;
    }

    setUploadError(null);
    setIsUploading(true);
    setResumeStatus('processing');

    try {
      const { uploadUrl } = await api.getResumeUploadUrl();
      await api.uploadResumeTos3(uploadUrl, file);
      setResumeFilename(file.name);
      // Status stays "processing" — the resume_parser Lambda will set it to "ready"
      // Poll on next page load via getSettings
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed. Please try again.');
      setResumeStatus(null);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleResumeDelete = async () => {
    setIsDeleting(true);
    setUploadError(null);
    try {
      await api.deleteResume();
      setResumeStatus(null);
      setResumeFilename(null);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Failed to delete resume.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleSave = async () => {
    if (settings) {
      updateSettings.mutate(
        {
          email: settings.email ?? '',
          dailyReport,
          weeklyReport,
          searchPreferences: {
            roleQueries,
            locations,
            salaryMin: salaryMin ? parseInt(salaryMin, 10) : null,
            salaryMax: salaryMax ? parseInt(salaryMax, 10) : null,
          },
          resumeStatus,
          resumeFilename,
        },
        {
          onSuccess: () => {
            setShowSuccess(true);
            setTimeout(() => setShowSuccess(false), 3000);
          },
        }
      );
    }
  };

  const inputClass =
    'w-full px-3 py-2 border border-slate-200 dark:border-gray-600 rounded-lg text-sm ' +
    'bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 ' +
    'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 dark:focus:ring-offset-gray-900 ' +
    'transition-colors';

  const sectionClass = 'mb-8 pb-8 border-b border-slate-200 dark:border-gray-700';
  const headingClass = 'text-lg font-semibold text-gray-900 dark:text-white mb-4';
  const labelClass = 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5';
  const chipClass =
    'inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 dark:bg-gray-700 ' +
    'text-gray-800 dark:text-gray-200 text-sm font-medium rounded-full';

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="animate-pulse">
          <div className="h-8 bg-slate-200 dark:bg-gray-700 rounded w-1/3 mb-8" />
          <div className="space-y-4">
            <div className="h-6 bg-slate-200 dark:bg-gray-700 rounded w-1/2" />
            <div className="h-12 bg-slate-200 dark:bg-gray-700 rounded" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-8">Settings</h1>

      <div className="bg-white dark:bg-gray-800 rounded-lg border border-slate-200 dark:border-gray-700 p-6 sm:p-8">

        {/* ── Search Preferences ── */}
        <div className={sectionClass}>
          <h2 className={headingClass}>Search Preferences</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
            Configure which roles, locations, and salary range the crawlers search for.
            Changes take effect on the next scheduled crawl.
          </p>

          {/* Job Roles */}
          <div className="mb-6">
            <label className={labelClass}>Job Roles</label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                placeholder="e.g. Security Engineer"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addRole())}
                className={inputClass}
              />
              <button
                type="button"
                onClick={addRole}
                disabled={!newRole.trim()}
                className="shrink-0 px-3 py-2 bg-primary text-white rounded-lg hover:bg-primary-700 disabled:opacity-40 transition-colors"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
            {roleQueries.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {roleQueries.map((role, i) => (
                  <span key={i} className={chipClass}>
                    {role}
                    <button onClick={() => removeRole(i)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            {roleQueries.length === 0 && (
              <p className="text-xs text-gray-400 dark:text-gray-500">
                No roles configured — defaults will be used (Security Engineer, Security Architect, etc.)
              </p>
            )}
          </div>

          {/* Locations */}
          <div className="mb-6">
            <label className={labelClass}>Locations</label>
            <div className="flex flex-col sm:flex-row gap-2 mb-2">
              <input
                type="text"
                placeholder="e.g. Atlanta, GA"
                value={newLocation}
                onChange={(e) => setNewLocation(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addLocation())}
                className={inputClass}
              />
              <div className="flex items-center gap-3 shrink-0">
                {!newRemote && (
                  <div className="flex items-center gap-1.5">
                    <label className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Radius</label>
                    <input
                      type="number"
                      min="0"
                      max="200"
                      value={newDistance ?? ''}
                      onChange={(e) => setNewDistance(e.target.value ? parseInt(e.target.value) : null)}
                      className="w-16 px-2 py-2 border border-slate-200 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200"
                    />
                    <span className="text-xs text-gray-400">mi</span>
                  </div>
                )}
                <label className="flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-300 cursor-pointer whitespace-nowrap">
                  <input
                    type="checkbox"
                    checked={newRemote}
                    onChange={(e) => setNewRemote(e.target.checked)}
                    className="accent-primary"
                  />
                  Remote
                </label>
                <button
                  type="button"
                  onClick={addLocation}
                  disabled={!newLocation.trim()}
                  className="shrink-0 px-3 py-2 bg-primary text-white rounded-lg hover:bg-primary-700 disabled:opacity-40 transition-colors"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
            {locations.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {locations.map((loc, i) => (
                  <span key={i} className={chipClass}>
                    <MapPin className="w-3.5 h-3.5 text-gray-400" />
                    {loc.location}
                    {loc.remote ? ' (Remote)' : loc.distance ? ` (${loc.distance} mi)` : ''}
                    <button onClick={() => removeLocation(i)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            {locations.length === 0 && (
              <p className="text-xs text-gray-400 dark:text-gray-500">
                No locations configured — defaults will be used (Atlanta 25mi + Remote US)
              </p>
            )}
          </div>

          {/* Salary Range */}
          <div>
            <label className={labelClass}>Salary Range (optional)</label>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 mb-1">Minimum</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                  <input
                    type="number"
                    min="0"
                    step="10000"
                    placeholder="No minimum"
                    value={salaryMin}
                    onChange={(e) => setSalaryMin(e.target.value)}
                    className={inputClass + ' pl-7'}
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 mb-1">Maximum</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                  <input
                    type="number"
                    min="0"
                    step="10000"
                    placeholder="No limit"
                    value={salaryMax}
                    onChange={(e) => setSalaryMax(e.target.value)}
                    className={inputClass + ' pl-7'}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Resume & AI Matching ── */}
        <div className={sectionClass}>
          <h2 className={headingClass}>Resume &amp; AI Matching</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
            Upload your resume (PDF) and Scout will automatically score each job posting against
            your background using Amazon Bedrock. Scores appear on every job card.
          </p>

          {/* Current resume state */}
          {resumeStatus === 'ready' && resumeFilename && (
            <div className="flex items-center gap-3 p-4 mb-4 rounded-lg bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800">
              <FileText className="w-5 h-5 text-green-600 dark:text-green-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-green-700 dark:text-green-300 truncate">
                  {resumeFilename}
                </p>
                <p className="text-xs text-green-600 dark:text-green-400">Resume ready — AI scoring active</p>
              </div>
              <button
                onClick={handleResumeDelete}
                disabled={isDeleting}
                className="shrink-0 p-1.5 text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900 rounded-md transition-colors disabled:opacity-50"
                title="Delete resume"
              >
                {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
              </button>
            </div>
          )}

          {resumeStatus === 'processing' && (
            <div className="flex items-center gap-3 p-4 mb-4 rounded-lg bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800">
              <Loader2 className="w-5 h-5 text-blue-600 dark:text-blue-400 shrink-0 animate-spin" />
              <p className="text-sm text-blue-700 dark:text-blue-300">
                Processing your resume… This usually takes under 30 seconds.
              </p>
            </div>
          )}

          {resumeStatus === 'error' && (
            <div className="flex items-center gap-3 p-4 mb-4 rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800">
              <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0" />
              <p className="text-sm text-red-700 dark:text-red-300">
                Resume processing failed (scanned PDF or corrupted file). Please upload a text-based PDF.
              </p>
            </div>
          )}

          {/* Upload control */}
          <div className="flex flex-col sm:flex-row items-start gap-3">
            <label className="flex-1 cursor-pointer">
              <div className={`flex items-center gap-2 px-4 py-2.5 border-2 border-dashed rounded-lg transition-colors ${
                isUploading
                  ? 'border-gray-200 dark:border-gray-600 text-gray-400'
                  : 'border-slate-300 dark:border-gray-600 hover:border-primary dark:hover:border-blue-500 text-gray-600 dark:text-gray-300 hover:text-primary dark:hover:text-blue-400'
              }`}>
                {isUploading
                  ? <Loader2 className="w-4 h-4 animate-spin shrink-0" />
                  : <Upload className="w-4 h-4 shrink-0" />
                }
                <span className="text-sm font-medium">
                  {isUploading ? 'Uploading…' : resumeStatus === 'ready' ? 'Replace Resume (PDF)' : 'Upload Resume (PDF)'}
                </span>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                className="sr-only"
                disabled={isUploading}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleResumeUpload(file);
                }}
              />
            </label>
          </div>

          {uploadError && (
            <p className="mt-2 text-sm text-red-600 dark:text-red-400 flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4 shrink-0" /> {uploadError}
            </p>
          )}
        </div>

        {/* ── Email Notifications ── */}
        <div className="mb-8">
          <h2 className={headingClass}>Email Notifications</h2>
          {settings?.email && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              Reports will be sent to <span className="font-medium text-gray-700 dark:text-gray-200">{settings.email}</span> (your account email).
            </p>
          )}
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 rounded-lg border border-slate-200 dark:border-gray-700 hover:border-slate-300 dark:hover:border-gray-600 transition-colors">
              <div>
                <label htmlFor="daily" className="text-gray-900 dark:text-gray-100 font-medium cursor-pointer">
                  Daily Report
                </label>
                <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
                  Receive a daily summary of new job postings
                </p>
              </div>
              <input
                id="daily"
                type="checkbox"
                checked={dailyReport}
                onChange={(e) => setDailyReport(e.target.checked)}
                className="w-5 h-5 text-primary rounded cursor-pointer accent-primary"
              />
            </div>

            <div className="flex items-center justify-between p-4 rounded-lg border border-slate-200 dark:border-gray-700 hover:border-slate-300 dark:hover:border-gray-600 transition-colors">
              <div>
                <label htmlFor="weekly" className="text-gray-900 dark:text-gray-100 font-medium cursor-pointer">
                  Weekly Report
                </label>
                <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
                  Receive a weekly summary of job postings and application status
                </p>
              </div>
              <input
                id="weekly"
                type="checkbox"
                checked={weeklyReport}
                onChange={(e) => setWeeklyReport(e.target.checked)}
                className="w-5 h-5 text-primary rounded cursor-pointer accent-primary"
              />
            </div>
          </div>
        </div>

        {/* ── Feedback ── */}
        {showSuccess && (
          <div className="mb-6 p-4 rounded-lg bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 flex items-center gap-3">
            <Check className="w-5 h-5 text-green-600 dark:text-green-400 shrink-0" />
            <p className="text-green-700 dark:text-green-300 font-medium">Settings saved successfully</p>
          </div>
        )}

        {updateSettings.error && (
          <div className="mb-6 p-4 rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0" />
            <p className="text-red-700 dark:text-red-300 font-medium">
              {updateSettings.error instanceof Error ? updateSettings.error.message : 'Failed to save settings'}
            </p>
          </div>
        )}

        {/* ── Save ── */}
        <div className="flex gap-3">
          <button
            onClick={handleSave}
            disabled={updateSettings.isPending}
            className="px-6 py-2.5 bg-primary text-white font-medium rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {updateSettings.isPending ? 'Saving…' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
