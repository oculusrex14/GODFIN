import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { fetchAuthStatus, logoutSession, setAuthToken } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isFirstRun, setIsFirstRun] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let retries = 0;
    const maxRetries = 5;
    let timeoutId = null;

    function checkStatus() {
      fetchAuthStatus()
        .then((data) => {
          setIsFirstRun(data.is_first_run);
          setLoading(false);
        })
        .catch(() => {
          retries++;
          if (retries < maxRetries) {
            // Backend may not be ready yet — retry after 1s
            timeoutId = setTimeout(checkStatus, 1000);
          } else {
            // Backend appears unreachable — default to NOT first-run (safer).
            // PinScreen will show "Enter Your PIN" with the offline shield.
            setIsFirstRun(false);
            setLoading(false);
          }
        });
    }

    checkStatus();

    // Cleanup: clear timeout on unmount
    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, []);

  const handleAuth = useCallback((token) => {
    setAuthToken(token);
    setIsAuthenticated(true);
    setIsFirstRun(false);
  }, []);

  const logout = useCallback(async () => {
    try {
      // Call backend logout endpoint to invalidate token server-side
      await logoutSession();
    } catch (e) {
      // Continue with logout even if backend call fails
      console.warn('Logout API call failed:', e);
    }
    setAuthToken(null);
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, isFirstRun, loading, handleAuth, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
