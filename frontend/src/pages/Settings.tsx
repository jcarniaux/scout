import { useState, useEffect } from 'react';
import { useSettings, useUpdateSettings } from '@/hooks/useJobs';
import { Check, AlertCircle } from 'lucide-react';

export function Settings() {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();
  const [localSettings, setLocalSettings] = useState({ dailyReport: false, weeklyReport: false });
  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    if (settings) {
      setLocalSettings({ dailyReport: settings.dailyReport, weeklyReport: settings.weeklyReport });
    }
  }, [settings]);

  const handleSave = async () => {
    if (settings) {
      updateSettings.mutate(
        { email: settings.email, ...localSettings },
        {
          onSuccess: () => {
            setShowSuccess(true);
            setTimeout(() => setShowSuccess(false), 3000);
          },
        }
      );
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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

        {/* Email Section */}
        <div className="mb-8 pb-8 border-b border-slate-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Email</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-500 dark:text-gray-400 text-sm">Notification email address</p>
              <p className="text-gray-900 dark:text-gray-100 font-medium mt-2">{settings?.email}</p>
            </div>
          </div>
        </div>

        {/* Email Preferences */}
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">Email Notifications</h2>
          <div className="space-y-4">

            {/* Daily Report */}
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
                checked={localSettings.dailyReport}
                onChange={(e) => setLocalSettings({ ...localSettings, dailyReport: e.target.checked })}
                className="w-5 h-5 text-primary rounded cursor-pointer accent-primary"
              />
            </div>

            {/* Weekly Report */}
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
                checked={localSettings.weeklyReport}
                onChange={(e) => setLocalSettings({ ...localSettings, weeklyReport: e.target.checked })}
                className="w-5 h-5 text-primary rounded cursor-pointer accent-primary"
              />
            </div>
          </div>
        </div>

        {/* Success Message */}
        {showSuccess && (
          <div className="mb-6 p-4 rounded-lg bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 flex items-center gap-3">
            <Check className="w-5 h-5 text-green-600 dark:text-green-400 shrink-0" />
            <p className="text-green-700 dark:text-green-300 font-medium">Settings saved successfully</p>
          </div>
        )}

        {/* Error Message */}
        {updateSettings.error && (
          <div className="mb-6 p-4 rounded-lg bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0" />
            <p className="text-red-700 dark:text-red-300 font-medium">
              {updateSettings.error instanceof Error ? updateSettings.error.message : 'Failed to save settings'}
            </p>
          </div>
        )}

        {/* Save */}
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
