import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuthenticator } from '@aws-amplify/ui-react';
import { fetchUserAttributes } from 'aws-amplify/auth';
import { Menu, X, Sun, Moon } from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';

export function Navbar() {
  const { signOut } = useAuthenticator((context) => [context.signOut]);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [email, setEmail] = useState<string>('');
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    fetchUserAttributes()
      .then((attrs) => setEmail(attrs.email ?? ''))
      .catch(() => setEmail(''));
  }, []);

  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-slate-200 dark:border-gray-700 shadow-sm sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">

          {/* Logo */}
          <Link to="/" className="flex items-center gap-2">
            <div className="text-xl font-bold text-primary">Scout</div>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-8">
            <Link
              to="/"
              className="text-gray-700 dark:text-gray-200 hover:text-primary dark:hover:text-primary font-medium transition-colors"
            >
              Dashboard
            </Link>
            <Link
              to="/settings"
              className="text-gray-700 dark:text-gray-200 hover:text-primary dark:hover:text-primary font-medium transition-colors"
            >
              Settings
            </Link>
            <div className="border-l border-slate-200 dark:border-gray-700 pl-8 flex items-center gap-3">
              <span className="text-sm text-gray-500 dark:text-gray-400">{email}</span>

              {/* Theme toggle */}
              <button
                onClick={toggleTheme}
                aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              </button>

              <button
                onClick={() => signOut()}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              >
                Sign Out
              </button>
            </div>
          </div>

          {/* Mobile — theme toggle + hamburger */}
          <div className="md:hidden flex items-center gap-1">
            <button
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 transition-colors"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-slate-200 dark:border-gray-700 py-4">
            <div className="flex flex-col gap-4">
              <Link
                to="/"
                className="text-gray-700 dark:text-gray-200 hover:text-primary dark:hover:text-primary font-medium"
                onClick={() => setMobileMenuOpen(false)}
              >
                Dashboard
              </Link>
              <Link
                to="/settings"
                className="text-gray-700 dark:text-gray-200 hover:text-primary dark:hover:text-primary font-medium"
                onClick={() => setMobileMenuOpen(false)}
              >
                Settings
              </Link>
              <div className="border-t border-slate-200 dark:border-gray-700 pt-4">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">{email}</p>
                <button
                  onClick={() => {
                    signOut();
                    setMobileMenuOpen(false);
                  }}
                  className="w-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                >
                  Sign Out
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
