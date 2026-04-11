import { useState, useEffect } from 'react';

type Theme = 'light' | 'dark';

/**
 * Manages light/dark theme.
 * - Persists the user's choice in localStorage.
 * - Falls back to the OS preference on first visit.
 * - Applies/removes the `dark` class on <html> so Tailwind's
 *   `darkMode: 'class'` strategy picks it up everywhere.
 */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem('scout-theme') as Theme | null;
    if (stored === 'light' || stored === 'dark') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('scout-theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === 'light' ? 'dark' : 'light'));

  return { theme, toggleTheme };
}
