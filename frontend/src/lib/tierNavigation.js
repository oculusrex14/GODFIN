export function lockedRouteMetadata(pathname, navigation) {
  const rule = navigation?.routes?.[pathname];
  if (!rule) return null;
  const features = new Set(navigation?.features || []);
  return features.has(rule.feature) ? null : rule;
}

export function navigationGroupsForLicense(groups, navigation) {
  return groups.map((group) => ({
    ...group,
    items: group.items.map((item) => ({
      ...item,
      lock: lockedRouteMetadata(item.to, navigation),
    })),
  }));
}
