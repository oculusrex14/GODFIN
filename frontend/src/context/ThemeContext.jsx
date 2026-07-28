import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const ThemeContext = createContext(null);

const THEME_STORAGE_KEY = 'godfin_theme';

export function ThemeProvider({ children }) {
  const [themeMode, setThemeMode] = useState(() => {
    // Load from localStorage on mount, default to 'dark-glass'
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      // Migrate old boolean theme to new string theme
      if (stored === 'light-glass') return 'light-glass';
      if (stored === 'liquid-glass') return 'light-glass'; // Old light theme becomes new light
      if (stored === 'default' || stored === null) return 'dark-glass';
      return stored;
    }
    return 'dark-glass';
  });

  // Apply theme to document when it changes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', themeMode);
    localStorage.setItem(THEME_STORAGE_KEY, themeMode);
  }, [themeMode]);

  const toggleTheme = useCallback(() => {
    setThemeMode(prev => prev === 'dark-glass' ? 'light-glass' : 'dark-glass');
  }, []);

  // For backward compatibility
  const glassThemeEnabled = themeMode === 'light-glass';

  return (
    <ThemeContext.Provider value={{ themeMode, glassThemeEnabled, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
