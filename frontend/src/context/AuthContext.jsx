import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { fetchAuthStatus, logoutSession, setAuthToken } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isFirstRun, setIsFirstRun] = useState(null);
  const [pinLength, setPinLength] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let retries = 0;
    const maxRetries = 5;
    let timeoutId = null;

    function checkStatus() {
      fetchAuthStatus()
        .then((data) => {
          setIsFirstRun(data.is_first_run);
          setPinLength(data.pin_length ?? null);
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
            setPinLength(null);
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

  const handleAuth = useCallback((token, configuredPinLength = null) => {
    setAuthToken(token);
    setIsAuthenticated(true);
    setIsFirstRun(false);
    if (configuredPinLength) setPinLength(configuredPinLength);
  }, []);

  const logout = useCallback(async () => {
    setIsAuthenticated(false);
    try {
      // The API client clears its memory-only token before awaiting the server.
      await logoutSession();
    } catch (e) {
      // The renderer remains locked even if the local backend is unavailable.
      console.warn('Logout API call failed:', e);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, isFirstRun, pinLength, loading, handleAuth, logout }}
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
