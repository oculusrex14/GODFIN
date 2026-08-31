/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

const RouterContext = createContext(null);

const ROUTER_BASE_PATH = (() => {
  const configured = import.meta.env.BASE_URL || '/';
  if (configured === '/') return '';
  return `/${configured.replace(/^\/+|\/+$/g, '')}`;
})();

function stripBasePath(pathname) {
  if (!ROUTER_BASE_PATH) return pathname;
  if (
    pathname === ROUTER_BASE_PATH
    || pathname === `${ROUTER_BASE_PATH}/`
    || pathname === `${ROUTER_BASE_PATH}/index.html`
  ) {
    return '/';
  }
  return pathname.startsWith(`${ROUTER_BASE_PATH}/`)
    ? pathname.slice(ROUTER_BASE_PATH.length)
    : pathname;
}

function withBasePath(pathname) {
  if (!ROUTER_BASE_PATH) return pathname;
  return pathname === '/'
    ? `${ROUTER_BASE_PATH}/index.html`
    : `${ROUTER_BASE_PATH}${pathname}`;
}

function browserLocation() {
  return {
    pathname: stripBasePath(window.location.pathname),
    search: window.location.search,
  };
}

export function RouterProvider({ children }) {
  const [location, setLocation] = useState(browserLocation);

  useEffect(() => {
    const handlePopState = () => setLocation(browserLocation());
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = useCallback((target, { replace = false } = {}) => {
    const url = new URL(target, window.location.origin);
    const method = replace ? 'replaceState' : 'pushState';
    window.history[method](null, '', `${withBasePath(url.pathname)}${url.search}${url.hash}`);
    setLocation(browserLocation());
  }, []);

  const value = useMemo(() => ({ ...location, navigate }), [location, navigate]);
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useLocation() {
  const context = useContext(RouterContext);
  if (!context) throw new Error('useLocation must be used within RouterProvider');
  return context;
}

export function Link({
  to,
  children,
  onClick,
  target,
  className,
  ...props
}) {
  const { navigate } = useLocation();
  return (
    <a
      {...props}
      className={className}
      href={to}
      target={target}
      onClick={(event) => {
        onClick?.(event);
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey ||
          target === '_blank'
        ) {
          return;
        }
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}

export function NavLink({ to, end = false, className, children, ...props }) {
  const { pathname } = useLocation();
  const targetPath = new URL(to, window.location.origin).pathname;
  const isActive = end
    ? pathname === targetPath
    : pathname === targetPath || (
      targetPath !== '/' && pathname.startsWith(`${targetPath}/`)
    );
  const resolvedClassName = typeof className === 'function'
    ? className({ isActive })
    : className;
  return (
    <Link {...props} className={resolvedClassName} to={to}>
      {children}
    </Link>
  );
}

export function Navigate({ to, replace = false }) {
  const { navigate } = useLocation();
  useEffect(() => {
    navigate(to, { replace });
  }, [navigate, replace, to]);
  return null;
}

export function useSearchParams() {
  const { pathname, search, navigate } = useLocation();
  const params = useMemo(() => new URLSearchParams(search), [search]);
  const setParams = useCallback((update, options = {}) => {
    const current = new URLSearchParams(window.location.search);
    const resolved = typeof update === 'function' ? update(current) : update;
    const next = resolved instanceof URLSearchParams
      ? resolved
      : new URLSearchParams(resolved);
    const query = next.toString();
    navigate(`${pathname}${query ? `?${query}` : ''}`, options);
  }, [navigate, pathname]);
  return [params, setParams];
}
