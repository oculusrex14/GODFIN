import { useEffect } from 'react';

import { subscribeToApiErrors } from '../api/errorEvents';
import { useToast } from '../context/ToastContext';

export default function GlobalErrorToasts() {
  const { error: showError } = useToast();

  useEffect(
    () =>
      subscribeToApiErrors((apiError) => {
        const message = apiError.hint
          ? `${apiError.message} ${apiError.hint}`
          : apiError.message;
        showError(message || 'GODFIN could not complete that request.');
      }),
    [showError],
  );

  return null;
}
