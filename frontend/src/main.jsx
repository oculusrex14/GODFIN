import React from 'react';
import ReactDOM from 'react-dom/client';
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import App from './App';
import { reportApiError } from './api/errorEvents';
import './index.css';

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: reportApiError,
  }),
  mutationCache: new MutationCache({
    onError: reportApiError,
  }),
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30000,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
