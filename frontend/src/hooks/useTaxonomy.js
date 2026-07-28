import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchTaxonomy } from '../api/client';

export function useTaxonomy() {
  const query = useQuery({
    queryKey: ['taxonomy'],
    queryFn: fetchTaxonomy,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const categories = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(query.data?.categories || {}).map(([category, data]) => [
          category,
          data.subcategories || [],
        ]),
      ),
    [query.data],
  );

  return {
    ...query,
    categories,
    categoryNames: query.data?.category_names || Object.keys(categories),
  };
}
