/** Build a safe OpenStreetMap URL from the best location data available. */
export function openStreetMapUrl({ mapUrl, lat, lon, name, location } = {}) {
  if (typeof mapUrl === 'string' && mapUrl.trim()) {
    try {
      const parsed = new URL(mapUrl);
      if (parsed.protocol === 'https:'
          && ['openstreetmap.org', 'www.openstreetmap.org'].includes(parsed.hostname)) {
        return parsed.href;
      }
    } catch { /* use coordinates or a place search instead */ }
  }

  const hasCoordinates = lat !== null && lat !== undefined && lat !== ''
    && lon !== null && lon !== undefined && lon !== '';
  if (hasCoordinates) {
    const latitude = Number(lat);
    const longitude = Number(lon);
    if (Number.isFinite(latitude) && Number.isFinite(longitude)
        && latitude >= -90 && latitude <= 90
        && longitude >= -180 && longitude <= 180) {
      return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`;
    }
  }

  const terms = [];
  for (const value of [name, location]) {
    const term = String(value || '').trim();
    if (term && !terms.some(existing => existing.toLowerCase() === term.toLowerCase())) {
      terms.push(term);
    }
  }
  if (!terms.length) return null;
  return `https://www.openstreetmap.org/search?query=${encodeURIComponent(terms.join(', '))}`;
}
