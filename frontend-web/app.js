/**
 * PlanWise AI — Frontend Application Controller
 * Multi-theme · location-aware · date-aware interactive planning
 */

// --- Configuration & API ---
// Same origin everywhere: the Vite dev server proxies /api to the backend, and in
// production the backend serves this page itself. Only a file opened straight
// from disk needs an absolute URL.
const API_BASE = window.location.protocol === 'file:'
  ? 'http://127.0.0.1:8000/api/v1'
  : '/api/v1';

const REQUEST_TIMEOUT_MS = 180000;
const MAX_TRIP_DAYS = 14;
const LOCATION_STORAGE_KEY = 'planwise_location';

let currentSessionId = null;
let isWaitingResponse = false;
let limitedMode = false;

/**
 * The location every request is planned for.
 *   activeLocation — what the user picked (or their current position)
 *   gpsLocation    — the device position, kept separately so "near me" works
 * Shape: { name, label, lat, lon, source: 'gps' | 'picked' | 'session' }
 */
let activeLocation = null;
let gpsLocation = null;

// --- DOM Elements ---
const $ = id => document.getElementById(id);

const viewLanding = $('view-landing');
const viewPlanner = $('view-planner');
const navExplore = $('nav-explore');
const navPlanner = $('nav-planner');
const navBrand = $('nav-brand');
const btnLaunchPlanner = $('btn-launch-planner');
const btnBackExplore = $('btn-back-explore');
const btnNewChat = $('btn-new-chat');

const chatMessages = $('chat-messages');
const chatInput = $('chat-input');
const btnChatSend = $('btn-chat-send');
const statusDot = $('status-dot');
const llmBadge = $('llm-badge');
const modeBanner = $('mode-banner');

const searchWhere = $('search-where');
const searchWhereResults = $('search-where-results');
const btnLocate = $('btn-locate');
const searchStart = $('search-start');
const searchEnd = $('search-end');
const searchExperience = $('search-experience');
const searchBudget = $('search-budget');
const btnCapsuleSearch = $('btn-capsule-search');
const capsuleHint = $('capsule-hint');
const searchCapsule = $('search-capsule');

const locationChip = $('location-chip');
const locationChipLabel = $('location-chip-label');
const locationPopover = $('location-popover');
const chipWhere = $('chip-where');
const chipWhereResults = $('chip-where-results');
const btnChipLocate = $('btn-chip-locate');

const itineraryEmptyState = $('itinerary-empty-state');
const itineraryContent = $('itinerary-content');
const planStatLocation = $('plan-stat-location');
const planStatDatesRow = $('plan-stat-dates-row');
const planStatDates = $('plan-stat-dates');
const planStatDuration = $('plan-stat-duration');
const planStatCost = $('plan-stat-cost');
const planStatValidation = $('plan-stat-validation');
const planWarnings = $('plan-warnings');
const planTimelineContainer = $('plan-timeline-container');

const DESTINATIONS = [
  { name: 'Paris', country: 'France', tag: 'Art · Cafés · Riverside walks', img: 'photo-1502602898657-3e91760cbb34' },
  { name: 'Tokyo', country: 'Japan', tag: 'Food · Neon · Temples', img: 'photo-1540959733332-eab4deabeeaf' },
  { name: 'Jaipur', country: 'India', tag: 'Forts · Palaces · Bazaars', img: 'photo-1477587458883-47145ed94245' },
  { name: 'London', country: 'United Kingdom', tag: 'Museums · Theatre · Parks', img: 'photo-1513635269975-59663e0ac1ad' },
  { name: 'Dubai', country: 'United Arab Emirates', tag: 'Skyline · Souks · Desert', img: 'photo-1512453979798-5ea266f8880c' },
  { name: 'New York', country: 'United States', tag: 'Skyscrapers · Broadway · Food', img: 'photo-1496442226666-8d4d0e62e6e9' },
  { name: 'Bali', country: 'Indonesia', tag: 'Temples · Rice terraces · Beaches', img: 'photo-1537996194471-e657df975ab4' },
  { name: 'Cambridge', country: 'United Kingdom', tag: 'Colleges · Punting · Museums', img: 'photo-1569154941061-e231b4725ef1' },
];


/* =====================================================================
   0. SMALL UTILITIES
   ===================================================================== */
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Only http(s) links are ever rendered as clickable. */
function safeUrl(url) {
  if (!url) return null;
  try {
    const candidate = /^https?:\/\//i.test(url) ? url : `https://${url}`;
    const parsed = new URL(candidate);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

function toISODate(d) {
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function parseISODate(iso) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || '')) return null;
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return Number.isNaN(date.getTime()) ? null : date;
}

function addDays(iso, days) {
  const d = parseISODate(iso);
  if (!d) return iso;
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

function daysBetween(startIso, endIso) {
  const a = parseISODate(startIso);
  const b = parseISODate(endIso);
  if (!a || !b) return null;
  return Math.round((b - a) / 86400000) + 1;
}

function prettyDate(iso, withWeekday = false) {
  const d = parseISODate(iso);
  if (!d) return iso || '';
  const opts = { day: 'numeric', month: 'short', year: 'numeric' };
  if (withWeekday) opts.weekday = 'short';
  return d.toLocaleDateString('en-GB', opts);
}

function formatMoney(amount, currency) {
  if (amount === null || amount === undefined || Number.isNaN(Number(amount))) return '';
  const value = Math.round(Number(amount));
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency', currency, maximumFractionDigits: 0,
      }).format(value);
    } catch { /* unknown currency code: fall through */ }
  }
  return `${currency ? currency + ' ' : ''}${value.toLocaleString()}`;
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

async function apiFetch(path, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${API_BASE}${path}`, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** Activate with Enter/Space for elements that act as buttons. */
function onActivate(el, handler) {
  el.addEventListener('click', handler);
  el.addEventListener('keydown', e => {
    if (e.target !== el) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handler(e);
    }
  });
}


/* =====================================================================
   1. THEME ENGINE (Light / Dark / System Default)
   ===================================================================== */
function initTheme() {
  let savedTheme = 'light';
  try { savedTheme = localStorage.getItem('planwise_theme') || 'light'; } catch { /* storage blocked */ }
  applyTheme(savedTheme);

  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', () => applyTheme(btn.getAttribute('data-theme-val')));
  });
}

function applyTheme(theme) {
  try { localStorage.setItem('planwise_theme', theme); } catch { /* storage blocked */ }
  document.documentElement.setAttribute('data-theme', theme);
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-theme-val') === theme);
  });
}


/* =====================================================================
   2. VIEW MANAGEMENT (Landing vs Planner)
   ===================================================================== */
function switchView(viewName) {
  const planner = viewName === 'planner';
  viewLanding.style.display = planner ? 'none' : 'block';
  viewPlanner.style.display = planner ? 'block' : 'none';
  navExplore.classList.toggle('active', !planner);
  navPlanner.classList.toggle('active', planner);
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (planner) {
    chatInput.focus({ preventScroll: true });
    ensureSession();
  }
}

function setupNavigation() {
  onActivate(navExplore, () => switchView('landing'));
  onActivate(navPlanner, () => switchView('planner'));
  onActivate(navBrand, () => switchView('landing'));
  btnLaunchPlanner.addEventListener('click', () => switchView('planner'));
  btnBackExplore.addEventListener('click', () => switchView('landing'));

  onActivate($('nav-how'), () => {
    switchView('landing');
    const howSection = $('how-it-works-section');
    if (howSection) {
      // wait for the landing view to be displayed before scrolling to it
      requestAnimationFrame(() => howSection.scrollIntoView({ behavior: 'smooth' }));
    }
  });

  btnNewChat.addEventListener('click', resetChat);
}


/* =====================================================================
   3. LOCATION: current position, picker, persistence
   ===================================================================== */
function setActiveLocation(place, { persist = true } = {}) {
  activeLocation = place ? {
    name: place.name || (place.label || '').split(',')[0],
    label: place.label || place.name,
    lat: place.lat,
    lon: place.lon,
    source: place.source || 'picked',
  } : null;

  if (persist) {
    try {
      if (activeLocation) localStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify(activeLocation));
      else localStorage.removeItem(LOCATION_STORAGE_KEY);
    } catch { /* storage blocked */ }
  }
  renderLocation();
}

function renderLocation() {
  const name = activeLocation ? activeLocation.name : null;
  const label = activeLocation ? activeLocation.label : null;

  if (document.activeElement !== searchWhere) searchWhere.value = label || '';
  locationChipLabel.textContent = label || 'Set location';
  locationChip.classList.toggle('is-empty', !label);

  const hero = $('hero-location');
  if (hero) hero.textContent = name || 'anywhere';
  document.querySelectorAll('.loc-name').forEach(el => { el.textContent = name || 'your city'; });
  document.querySelectorAll('.loc-inline').forEach(el => { el.textContent = label || 'your chosen location'; });
}

function restoreLocation() {
  try {
    const saved = JSON.parse(localStorage.getItem(LOCATION_STORAGE_KEY) || 'null');
    if (saved && typeof saved.lat === 'number' && typeof saved.lon === 'number' && saved.label) {
      setActiveLocation(saved, { persist: false });
      if (saved.source === 'gps') gpsLocation = { ...activeLocation };
      return true;
    }
  } catch { /* corrupted value: ignore */ }
  return false;
}

function setCapsuleHint(text, isError = false) {
  capsuleHint.textContent = text || '';
  capsuleHint.classList.toggle('is-error', Boolean(isError));
}

/**
 * Resolve the device position to a named place.
 * @param {boolean} adopt  make it the active location when found
 * @param {boolean} quiet  no error hints (used for the automatic attempt on load)
 */
function detectCurrentLocation({ adopt = true, quiet = false } = {}) {
  return new Promise(resolve => {
    if (!('geolocation' in navigator)) {
      if (!quiet) setCapsuleHint('Location is not available in this browser — type a city instead.', true);
      resolve(null);
      return;
    }
    if (!quiet) setCapsuleHint('Finding your location…');
    btnLocate.classList.add('is-busy');

    navigator.geolocation.getCurrentPosition(async position => {
      const { latitude, longitude } = position.coords;
      try {
        const res = await apiFetch(`/geo/reverse?lat=${latitude.toFixed(5)}&lon=${longitude.toFixed(5)}`, {}, 20000);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const place = await res.json();
        gpsLocation = { name: place.name, label: place.label, lat: place.lat, lon: place.lon, source: 'gps' };
        if (adopt) setActiveLocation(gpsLocation);
        if (!quiet) setCapsuleHint(`Using your current location: ${place.label}`);
        resolve(gpsLocation);
      } catch (err) {
        console.warn('Reverse geocoding failed:', err);
        if (!quiet) setCapsuleHint('Found your position but could not name it — is the backend running?', true);
        resolve(null);
      } finally {
        btnLocate.classList.remove('is-busy');
      }
    }, error => {
      btnLocate.classList.remove('is-busy');
      if (!quiet) {
        const denied = error.code === error.PERMISSION_DENIED;
        setCapsuleHint(
          denied
            ? 'Location permission was denied — type a city, or allow location access in your browser.'
            : 'Could not get your location — type a city instead.',
          true,
        );
      }
      resolve(null);
    }, { enableHighAccuracy: false, timeout: 12000, maximumAge: 600000 });
  });
}

/** Use the current position automatically on first load, without nagging. */
async function initLocation() {
  if (restoreLocation()) return;
  await detectCurrentLocation({ adopt: true, quiet: true });
  if (!activeLocation) {
    setCapsuleHint('Tip: tap 📍 to use your current location, or type any city.');
  }
}

/**
 * Autocomplete behaviour shared by the search bar and the planner popover.
 */
function createPlacePicker(input, dropdown, onPick) {
  let items = [];
  let highlighted = -1;
  let requestId = 0;

  const close = () => {
    dropdown.classList.remove('is-open');
    dropdown.innerHTML = '';
    input.setAttribute('aria-expanded', 'false');
    items = [];
    highlighted = -1;
  };

  const render = (message) => {
    if (message) {
      dropdown.innerHTML = `<div class="place-option is-note">${escapeHtml(message)}</div>`;
    } else {
      dropdown.innerHTML = items.map((p, i) => `
        <div class="place-option${i === highlighted ? ' is-active' : ''}" role="option" data-index="${i}">
          <span class="place-option-icon">📍</span>
          <span>
            <span class="place-option-name">${escapeHtml(p.name)}</span>
            <span class="place-option-detail">${escapeHtml(p.display_name || p.label)}</span>
          </span>
        </div>`).join('');
    }
    dropdown.classList.add('is-open');
    input.setAttribute('aria-expanded', 'true');
  };

  const pick = index => {
    const place = items[index];
    if (!place) return;
    input.value = place.label;
    close();
    onPick({ name: place.name, label: place.label, lat: place.lat, lon: place.lon, source: 'picked' });
  };

  const search = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) { close(); return; }
    const myRequest = ++requestId;
    render('Searching…');
    try {
      const res = await apiFetch(`/geo/search?q=${encodeURIComponent(q)}`, {}, 20000);
      if (myRequest !== requestId) return;           // a newer keystroke won
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      items = await res.json();
      highlighted = items.length ? 0 : -1;
      render(items.length ? null : 'No places found — try a different spelling.');
    } catch (err) {
      if (myRequest !== requestId) return;
      items = [];
      render('Place search is unavailable — is the backend running?');
    }
  }, 350);

  input.addEventListener('input', search);
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' && items.length) {
      e.preventDefault(); highlighted = (highlighted + 1) % items.length; render();
    } else if (e.key === 'ArrowUp' && items.length) {
      e.preventDefault(); highlighted = (highlighted - 1 + items.length) % items.length; render();
    } else if (e.key === 'Enter') {
      if (items.length && highlighted >= 0) { e.preventDefault(); pick(highlighted); }
    } else if (e.key === 'Escape') {
      close();
    }
  });
  // mousedown fires before the input's blur, so the pick is not lost
  dropdown.addEventListener('mousedown', e => {
    const option = e.target.closest('.place-option[data-index]');
    if (option) { e.preventDefault(); pick(Number(option.dataset.index)); }
  });
  input.addEventListener('blur', () => setTimeout(close, 150));

  return { close };
}

function prefetchLocation(place) {
  if (!place) return;
  apiFetch(`/geo/prefetch?lat=${place.lat}&lon=${place.lon}`, { method: 'POST' }, 10000).catch(() => {});
}

/** Geocode a typed name that was never picked from the dropdown. */
async function resolveTypedLocation(text) {
  try {
    const res = await apiFetch(`/geo/search?q=${encodeURIComponent(text)}`, {}, 20000);
    if (!res.ok) return null;
    const results = await res.json();
    if (!results.length) return null;
    const p = results[0];
    return { name: p.name, label: p.label, lat: p.lat, lon: p.lon, source: 'picked' };
  } catch {
    return null;
  }
}

function setupLocationControls() {
  // Search bar on the home page
  createPlacePicker(searchWhere, searchWhereResults, place => {
    setActiveLocation(place);
    setCapsuleHint('');
    prefetchLocation(place);
  });
  searchWhere.addEventListener('focus', () => searchWhere.select());
  searchWhere.addEventListener('input', () => {
    if (!searchWhere.value.trim()) setActiveLocation(null);
  });
  btnLocate.addEventListener('click', () => detectCurrentLocation({ adopt: true }));

  // Location chip in the planner header
  const chipPicker = createPlacePicker(chipWhere, chipWhereResults, place => {
    setActiveLocation(place);
    prefetchLocation(place);
    togglePopover(false);
  });

  function togglePopover(open) {
    locationPopover.classList.toggle('is-open', open);
    locationChip.setAttribute('aria-expanded', String(open));
    if (open) {
      chipWhere.value = '';
      chipWhere.focus();
    } else {
      chipPicker.close();
    }
  }

  locationChip.addEventListener('click', e => {
    e.stopPropagation();
    togglePopover(!locationPopover.classList.contains('is-open'));
  });
  locationPopover.addEventListener('click', e => e.stopPropagation());
  document.addEventListener('click', () => togglePopover(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') togglePopover(false); });

  btnChipLocate.addEventListener('click', async () => {
    btnChipLocate.disabled = true;
    btnChipLocate.textContent = 'Finding your location…';
    const found = await detectCurrentLocation({ adopt: true, quiet: true });
    btnChipLocate.disabled = false;
    btnChipLocate.textContent = found ? '📍 Use my current location' : '⚠️ Location unavailable — type a city';
    if (found) togglePopover(false);
  });
}


/* =====================================================================
   4. DATE RANGE (home page search bar)
   ===================================================================== */
function setupDateInputs() {
  const today = toISODate(new Date());
  searchStart.min = today;
  searchEnd.min = today;

  searchStart.addEventListener('change', () => {
    const start = searchStart.value;
    if (!start) { searchEnd.min = today; return; }
    searchEnd.min = start;
    searchEnd.max = addDays(start, MAX_TRIP_DAYS - 1);
    if (!searchEnd.value || searchEnd.value < start) {
      searchEnd.value = addDays(start, 1);
    } else if (searchEnd.value > searchEnd.max) {
      searchEnd.value = searchEnd.max;
      setCapsuleHint(`Trips are limited to ${MAX_TRIP_DAYS} days — end date adjusted.`);
    }
  });

  searchEnd.addEventListener('change', () => {
    if (searchStart.value && searchEnd.value && searchEnd.value < searchStart.value) {
      searchEnd.value = searchStart.value;
    }
    if (!searchStart.value && searchEnd.value) {
      // an end date alone: assume a start today (or the end day itself if earlier)
      searchStart.value = searchEnd.value < today ? searchEnd.value : today;
      if (daysBetween(searchStart.value, searchEnd.value) > MAX_TRIP_DAYS) {
        searchStart.value = addDays(searchEnd.value, -(MAX_TRIP_DAYS - 1));
      }
    }
  });
}

/** Validated date range from the search bar: { start, end, days } or null. */
function getSelectedDates() {
  let start = searchStart.value || null;
  let end = searchEnd.value || null;
  if (!start && !end) return null;
  if (start && !end) end = start;
  if (!start && end) start = end;
  if (end < start) [start, end] = [end, start];
  let days = daysBetween(start, end);
  if (days > MAX_TRIP_DAYS) {
    end = addDays(start, MAX_TRIP_DAYS - 1);
    days = MAX_TRIP_DAYS;
  }
  return { start, end, days };
}

function describeDates(dates) {
  if (!dates) return '';
  if (dates.start === dates.end) return `on ${prettyDate(dates.start)}`;
  return `from ${prettyDate(dates.start)} to ${prettyDate(dates.end)}`;
}


/* =====================================================================
   5. API CLIENT & SESSION MANAGEMENT
   ===================================================================== */
let sessionPromise = null;

function ensureSession(forceNew = false) {
  if (currentSessionId && !forceNew) return Promise.resolve(currentSessionId);
  // callers that arrive while a session is being created share that request
  if (sessionPromise && !forceNew) return sessionPromise;

  const request = (async () => {
    try {
      const res = await apiFetch('/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      }, 20000);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      currentSessionId = data.session_id;
      return currentSessionId;
    } catch (err) {
      console.error('Session creation failed:', err);
      currentSessionId = null;
      return null;
    } finally {
      if (sessionPromise === request) sessionPromise = null;
    }
  })();
  sessionPromise = request;
  return request;
}

async function checkBackendHealth() {
  try {
    const res = await apiFetch('/health', {}, 15000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    limitedMode = Boolean(data.limited_mode);

    statusDot.classList.remove('is-offline');
    statusDot.classList.toggle('is-limited', limitedMode);
    statusDot.title = limitedMode ? 'AI online (free keyless mode)' : 'AI online';
    llmBadge.textContent = data.llm_provider ? `AI: ${data.llm_provider}` : '';

    if (limitedMode) {
      modeBanner.hidden = false;
      modeBanner.textContent =
        'Free keyless AI mode: about one AI-written reply every 45 seconds (live data is always instant). ' +
        'Add a free GROQ_API_KEY or GEMINI_API_KEY to the .env file for fast, unlimited-feeling answers.';
    } else {
      modeBanner.hidden = true;
    }
  } catch (err) {
    statusDot.classList.add('is-offline');
    statusDot.title = 'Backend unreachable';
    llmBadge.textContent = 'offline';
    console.warn('Backend currently unreachable on', API_BASE);
  }
}

function welcomeMessageHtml(reset = false) {
  const where = activeLocation ? ` in <strong>${escapeHtml(activeLocation.label)}</strong>` : '';
  return `
    <div class="message-row assistant">
      <div class="message-avatar">🗺️</div>
      <div class="message-bubble">
        <p><strong>${reset ? 'Fresh start!' : 'Welcome to PlanWise AI!'}</strong></p>
        <p>I find real hotels, restaurants, attractions and transport hubs from live map data${where || ' anywhere in the world'}, and turn them into day-by-day itineraries with dates and a budget.</p>
        <p>Use the 📍 chip above to change the location, or just name a place in your message.</p>
      </div>
    </div>`;
}

async function resetChat() {
  if (isWaitingResponse) return;
  currentSessionId = null;
  chatMessages.innerHTML = welcomeMessageHtml(true);
  itineraryEmptyState.style.display = 'block';
  itineraryContent.style.display = 'none';
  planTimelineContainer.innerHTML = '';
  await ensureSession(true);
}


/* =====================================================================
   6. CHAT INTERACTIONS
   ===================================================================== */
const NEAR_ME = /\b(near\s*me|nearby|around\s+me|around\s+here|close\s+to\s+me|my\s+(current\s+)?location|near\s+here)\b/i;

function buildContext(message, overrides = {}) {
  const context = {};
  let place = activeLocation;
  let explicit = Boolean(overrides.explicit);

  // "near me" always means the device position when we know it
  if (NEAR_ME.test(message) && gpsLocation) {
    place = gpsLocation;
    explicit = true;
  }
  if (place) {
    context.location = place.label;
    context.lat = place.lat;
    context.lon = place.lon;
  }
  if (overrides.dates) {
    context.start_date = overrides.dates.start;
    context.end_date = overrides.dates.end;
  }
  context.explicit = explicit;
  return Object.keys(context).length > 1 ? context : null;
}

function setBusy(busy) {
  isWaitingResponse = busy;
  btnChatSend.disabled = busy;
  chatInput.disabled = busy;
  btnCapsuleSearch.disabled = busy;
}

async function postMessage(sessionId, body) {
  return apiFetch(`/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/**
 * Send a message to the agent.
 * @param {string} text     message (defaults to the chat input)
 * @param {object} options  { explicit, dates } — values picked in the search bar
 */
async function handleUserSend(text, options = {}) {
  const query = (typeof text === 'string' ? text : chatInput.value).trim();
  if (!query || isWaitingResponse) return;

  // "near me" before we know where the user is: try to find out first
  if (NEAR_ME.test(query) && !gpsLocation && !activeLocation) {
    await detectCurrentLocation({ adopt: true, quiet: true });
  }

  chatInput.value = '';
  setBusy(true);
  appendMessage('user', query);
  const spinnerId = appendThinkingIndicator();

  try {
    let sessionId = await ensureSession();
    if (!sessionId) throw new Error('backend unreachable');

    const body = { message: query };
    const context = buildContext(query, options);
    if (context) body.context = context;

    let res = await postMessage(sessionId, body);
    if (res.status === 404) {
      // the backend restarted and forgot the session: start a new one, retry once
      sessionId = await ensureSession(true);
      if (!sessionId) throw new Error('backend unreachable');
      res = await postMessage(sessionId, body);
    }
    if (!res.ok) throw new Error(`server returned status ${res.status}`);

    const data = await res.json();
    removeThinkingIndicator(spinnerId);
    appendAssistantMessage(data.message || 'I have processed your request.', data);

    if (data.plan) renderItineraryDrawer(data.plan, data.validation, data.context || {});
    syncContextFromResponse(data.context);
    if (data.context && data.context.llm_provider) {
      llmBadge.textContent = `AI: ${data.context.llm_provider}`;
    }
  } catch (err) {
    removeThinkingIndicator(spinnerId);
    const timedOut = err.name === 'AbortError';
    appendMessage(
      'assistant',
      timedOut
        ? '⚠️ That took too long and was cancelled. Please try again — the free AI and map services are sometimes slow.'
        : `⚠️ Could not reach the PlanWise AI server (${err.message}). Please check that the backend is running on port 8000.`,
    );
    checkBackendHealth();
  } finally {
    setBusy(false);
    chatInput.focus({ preventScroll: true });
  }
}

/** Keep the location chip in step with what the agent actually used. */
function syncContextFromResponse(context) {
  if (!context || !context.location || context.lat === null || context.lat === undefined) return;
  const same = activeLocation
    && Math.abs(activeLocation.lat - context.lat) < 0.01
    && Math.abs(activeLocation.lon - context.lon) < 0.01;
  if (!same) {
    setActiveLocation({
      name: context.location.split(',')[0],
      label: context.location,
      lat: context.lat,
      lon: context.lon,
      source: 'session',
    });
  }
}

function scrollChatToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function createMessageRow(role) {
  const row = document.createElement('div');
  row.className = `message-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🗺️';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  row.appendChild(avatar);
  row.appendChild(bubble);
  return { row, bubble };
}

function appendMessage(role, content) {
  const { row, bubble } = createMessageRow(role);
  bubble.innerHTML = formatMarkdown(content);
  chatMessages.appendChild(row);
  scrollChatToBottom();
}

function appendThinkingIndicator() {
  const id = `thinking-${Date.now()}`;
  const { row, bubble } = createMessageRow('assistant');
  row.id = id;

  const steps = [
    'Understanding your request…',
    'Searching live map data…',
    'Asking the AI model…',
    limitedMode ? 'Still working — the free AI endpoint can take up to a minute…' : 'Putting the answer together…',
    'Checking dates, budget and details…',
  ];
  bubble.innerHTML = `
    <div class="thinking-indicator">
      <span class="thinking-spinner"></span>
      <span class="thinking-text">${escapeHtml(steps[0])}</span>
    </div>`;

  let step = 0;
  const label = bubble.querySelector('.thinking-text');
  row._timer = setInterval(() => {
    step = Math.min(step + 1, steps.length - 1);
    label.textContent = steps[step];
  }, 5000);

  chatMessages.appendChild(row);
  scrollChatToBottom();
  return id;
}

function removeThinkingIndicator(id) {
  const el = document.getElementById(id);
  if (!el) return;
  clearInterval(el._timer);
  el.remove();
}

function appendAssistantMessage(text, responseData) {
  const { row, bubble } = createMessageRow('assistant');
  let html = formatMarkdown(text);

  const results = Array.isArray(responseData.results) ? responseData.results : [];
  if (results.length) {
    html += '<div class="entity-cards-container">'
      + results.map(r => renderResultCard(r, responseData.results_domain)).join('')
      + '</div>';
  }

  const warnings = (responseData.validation && responseData.validation.warnings) || [];
  if (warnings.length && !responseData.plan) {
    html += `<div class="message-note is-warning">${warnings.map(w => `⚠️ ${escapeHtml(w)}`).join('<br/>')}</div>`;
  }

  const notice = responseData.context && responseData.context.notice;
  if (notice) {
    html += `<div class="message-note">ℹ️ ${escapeHtml(notice)}</div>`;
  }

  bubble.innerHTML = html;
  chatMessages.appendChild(row);
  // show the start of long answers instead of jumping past them
  // (scroll only the chat pane, never the whole page)
  const top = row.getBoundingClientRect().top - chatMessages.getBoundingClientRect().top;
  chatMessages.scrollTo({ top: chatMessages.scrollTop + top - 12, behavior: 'smooth' });
}

const DOMAIN_ICONS = { hotel: '🏨', restaurant: '🍽️', attraction: '🏛️', transport: '🚆' };

/** A result card built from structured data returned by the backend. */
function renderResultCard(r, domain) {
  const badges = [];
  if (r.stars && Number(r.stars) > 0) badges.push(`${'★'.repeat(Math.min(Number(r.stars), 5))}`);
  if (r.food) badges.push(r.food);
  if (r.vegetarian) badges.push(r.vegetarian === 'only' ? '🌱 Vegetarian only' : '🌱 Vegetarian options');
  if (r.vegan) badges.push('Vegan options');
  if (r.pricerange) badges.push(r.pricerange);
  if (r.entrance_fee && r.entrance_fee !== '?') badges.push(`Entry: ${r.entrance_fee}`);
  if (r.code) badges.push(r.code);
  if (r.internet === 'yes') badges.push('Wi-Fi');
  if (r.parking === 'yes') badges.push('Parking');
  if (r.leaveAt && r.arriveBy) badges.push(`${r.leaveAt} → ${r.arriveBy}`);
  if (r.day) badges.push(r.day);
  if (r.duration) badges.push(r.duration);
  if (r.price) badges.push(r.price);

  const subtitleParts = [];
  if (r.type) subtitleParts.push(r.type);
  if (r.area) subtitleParts.push(r.area);
  if (typeof r.distance_km === 'number') subtitleParts.push(`${r.distance_km} km from centre`);

  const details = [];
  if (r.address) details.push(`<div>📍 ${escapeHtml(r.address)}</div>`);
  if (r.opening_hours) details.push(`<div>🕒 ${escapeHtml(r.opening_hours)}</div>`);
  if (r.phone) details.push(`<div>📞 ${escapeHtml(r.phone)}</div>`);

  const links = [];
  const mapUrl = safeUrl(r.map_url)
    || (typeof r.lat === 'number' && typeof r.lon === 'number'
      ? `https://www.openstreetmap.org/?mlat=${r.lat}&mlon=${r.lon}#map=17/${r.lat}/${r.lon}` : null);
  if (mapUrl) links.push(`<a href="${escapeHtml(mapUrl)}" target="_blank" rel="noopener noreferrer">View on map ↗</a>`);
  const site = safeUrl(r.website);
  if (site) links.push(`<a href="${escapeHtml(site)}" target="_blank" rel="noopener noreferrer">Website ↗</a>`);

  return `
    <div class="entity-result-card">
      <div class="entity-card-header">
        <span class="entity-card-name">${DOMAIN_ICONS[domain] || '📌'} ${escapeHtml(r.name || 'Unnamed place')}</span>
      </div>
      ${subtitleParts.length ? `<div class="entity-card-type">${escapeHtml(subtitleParts.join(' · '))}</div>` : ''}
      ${badges.length ? `<div class="entity-card-badges">${badges.map(b => `<span>${escapeHtml(b)}</span>`).join('')}</div>` : ''}
      ${details.length ? `<div class="entity-card-details">${details.join('')}</div>` : ''}
      ${links.length ? `<div class="entity-card-links">${links.join('')}</div>` : ''}
    </div>`;
}

/**
 * Small, safe Markdown → HTML formatter (everything is escaped first).
 * Supports headings, bold, italics, bullet and numbered lists, paragraphs.
 */
function formatMarkdown(md) {
  if (!md) return '';

  const inline = raw => escapeHtml(raw)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>')
    .replace(/(^|[\s(])_([^_\s][^_]*?)_(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');

  const out = [];
  let list = null;           // 'ul' | 'ol' | null
  let paragraph = [];

  const flushParagraph = () => {
    if (paragraph.length) { out.push(`<p>${paragraph.join('<br/>')}</p>`); paragraph = []; }
  };
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };

  String(md).replace(/\r\n/g, '\n').split('\n').forEach(line => {
    const trimmed = line.trim();
    if (!trimmed) { flushParagraph(); closeList(); return; }

    const heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushParagraph(); closeList();
      const tag = heading[1].length <= 2 ? 'h3' : 'h4';
      out.push(`<${tag} class="md-heading">${inline(heading[2])}</${tag}>`);
      return;
    }
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) { flushParagraph(); closeList(); out.push('<hr class="md-rule"/>'); return; }

    const bullet = trimmed.match(/^[-*•]\s+(.*)$/);
    const numbered = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
    if (bullet || numbered) {
      flushParagraph();
      const wanted = bullet ? 'ul' : 'ol';
      if (list !== wanted) { closeList(); out.push(`<${wanted} class="md-list">`); list = wanted; }
      out.push(`<li>${inline(bullet ? bullet[1] : numbered[2])}</li>`);
      return;
    }

    closeList();
    paragraph.push(inline(trimmed));
  });

  flushParagraph();
  closeList();
  return out.join('');
}


/* =====================================================================
   7. ITINERARY & BUDGET DRAWER RENDERER
   ===================================================================== */
const ACTIVITY_ICONS = {
  attraction: '🎯', restaurant: '🍽️', hotel: '🏨', transport: '🚆', study: '📖', break: '☕',
};

function renderItineraryDrawer(plan, validation, context) {
  if (!plan) return;

  const currency = plan.currency || context.currency || null;
  itineraryEmptyState.style.display = 'none';
  itineraryContent.style.display = 'block';

  planStatLocation.textContent = plan.location || (plan.plan_type === 'study' ? 'Study schedule' : '-');

  if (plan.start_date) {
    planStatDatesRow.style.display = '';
    planStatDates.textContent = plan.end_date && plan.end_date !== plan.start_date
      ? `${prettyDate(plan.start_date)} → ${prettyDate(plan.end_date)}`
      : prettyDate(plan.start_date);
  } else {
    planStatDatesRow.style.display = 'none';
  }

  const dayCount = plan.duration_days || (plan.days ? plan.days.length : 1);
  planStatDuration.textContent = `${dayCount} day${dayCount === 1 ? '' : 's'}`;

  if (plan.estimated_total_cost !== undefined && plan.estimated_total_cost !== null) {
    let cost = formatMoney(plan.estimated_total_cost, currency);
    if (context.budget) cost += ` / ${formatMoney(context.budget, currency)}`;
    planStatCost.textContent = cost;
  } else {
    planStatCost.textContent = plan.plan_type === 'study' ? 'Free' : 'Not estimated';
  }

  const invalid = validation && validation.valid === false;
  planStatValidation.textContent = invalid ? '⚠️ Constraints not met' : '✓ Constraints verified';
  planStatValidation.style.color = invalid ? 'var(--warning)' : 'var(--success)';

  const notes = [
    ...((validation && validation.violations) || []),
    ...((validation && validation.warnings) || []),
  ];
  if (notes.length) {
    planWarnings.hidden = false;
    planWarnings.innerHTML = notes.map(n => `<div>⚠️ ${escapeHtml(n)}</div>`).join('');
  } else {
    planWarnings.hidden = true;
    planWarnings.innerHTML = '';
  }

  planTimelineContainer.innerHTML = '';
  (plan.days || []).forEach(day => {
    const dayEl = document.createElement('div');
    dayEl.className = 'timeline-day';

    let slotsHtml = '';
    (day.slots || []).forEach(slot => {
      const activities = slot.activities || [];
      if (!activities.length) return;

      const actsHtml = activities.map(a => {
        const details = a.details || {};
        const cost = a.estimated_cost ? formatMoney(a.estimated_cost, currency)
          : (a.estimated_cost === 0 && a.type === 'attraction' ? 'Free' : '');
        const suggested = details.source === 'ai_suggested';
        const mapUrl = safeUrl(details.map_url);
        return `
          <div class="slot-activity">
            <div class="slot-activity-main">
              ${a.start_time ? `<span class="slot-clock">${escapeHtml(a.start_time)}</span>` : ''}
              <span class="slot-name">${ACTIVITY_ICONS[a.type] || '•'} ${escapeHtml(a.name)}</span>
              ${cost ? `<span class="slot-cost">${escapeHtml(cost)}</span>` : ''}
            </div>
            ${details.note ? `<div class="slot-note">${escapeHtml(details.note)}</div>` : ''}
            <div class="slot-meta">
              ${suggested ? '<span class="slot-tag" title="Suggested by the AI, not found in the live map data">AI suggestion</span>' : ''}
              ${mapUrl ? `<a href="${escapeHtml(mapUrl)}" target="_blank" rel="noopener noreferrer">Map ↗</a>` : ''}
            </div>
          </div>`;
      }).join('');

      slotsHtml += `
        <div class="timeline-slot">
          <div class="slot-time">${escapeHtml(slot.time_of_day || 'Slot')}</div>
          ${actsHtml}
        </div>`;
    });

    if (!slotsHtml) {
      slotsHtml = '<div class="timeline-slot"><div class="slot-activity" style="color:var(--text-muted); font-weight:400;">Free day</div></div>';
    }

    dayEl.innerHTML = `
      <div class="timeline-day-title">
        <span>📅</span> Day ${escapeHtml(day.day || 1)}
        ${day.date ? `<span class="timeline-day-date">${escapeHtml(prettyDate(day.date, true))}</span>` : ''}
      </div>
      ${slotsHtml}`;
    planTimelineContainer.appendChild(dayEl);
  });
}


/* =====================================================================
   8. PROMPT CARDS, DESTINATIONS & SEARCH BAR BINDINGS
   ===================================================================== */
function fillPrompt(template) {
  if (!template.includes('{loc}')) return template;
  if (activeLocation) return template.replace('{loc}', activeLocation.name);
  // no location yet: "near me" phrasing lets the agent ask or use GPS
  return template
    .replace(/\s+(in|to|near)\s+\{loc\}/, ' near me')
    .replace('{loc}', 'my location');
}

function nudgeLocationInput(message) {
  switchView('landing');
  setCapsuleHint(message, true);
  searchCapsule.classList.remove('shake');
  void searchCapsule.offsetWidth;            // restart the animation
  searchCapsule.classList.add('shake');
  searchWhere.focus();
}

function renderDestinations() {
  const grid = $('destination-grid');
  grid.innerHTML = DESTINATIONS.map((d, i) => `
    <div class="dest-card" data-index="${i}" role="button" tabindex="0" aria-label="Plan a trip to ${escapeHtml(d.name)}">
      <div class="dest-image-wrap">
        <img src="https://images.unsplash.com/${d.img}?auto=format&fit=crop&w=600&q=80" alt="${escapeHtml(d.name)}" loading="lazy" />
      </div>
      <div class="dest-info">
        <div class="dest-title">${escapeHtml(d.name)}</div>
        <div class="dest-rating">${escapeHtml(d.country)}</div>
      </div>
      <div class="dest-area">${escapeHtml(d.tag)}</div>
      <div class="dest-price">Plan a trip <span>→</span></div>
    </div>`).join('');

  grid.querySelectorAll('img').forEach(img => {
    img.addEventListener('error', () => img.closest('.dest-image-wrap').classList.add('is-fallback'));
  });

  grid.querySelectorAll('.dest-card').forEach(card => {
    onActivate(card, async () => {
      if (isWaitingResponse) return;
      const dest = DESTINATIONS[Number(card.dataset.index)];
      const dates = getSelectedDates();
      const place = await resolveTypedLocation(`${dest.name}, ${dest.country}`);
      if (place) setActiveLocation(place);

      const message = dates
        ? `Plan a trip to ${dest.name} ${describeDates(dates)}`
        : `Plan a 2-day trip to ${dest.name}`;
      switchView('planner');
      handleUserSend(message, { explicit: Boolean(place), dates });
    });
  });
}

async function runCapsuleSearch() {
  if (isWaitingResponse) return;

  // A name that was typed but never picked from the list still counts
  const typed = searchWhere.value.trim();
  if (typed && (!activeLocation || activeLocation.label !== typed)) {
    setCapsuleHint('Looking up that place…');
    const place = await resolveTypedLocation(typed);
    if (!place) {
      nudgeLocationInput(`Couldn't find "${typed}" — pick a place from the suggestions.`);
      return;
    }
    setActiveLocation(place);
  }
  if (!activeLocation) {
    nudgeLocationInput('Choose a destination first — type a city or tap 📍 for your current location.');
    return;
  }
  setCapsuleHint('');

  const where = activeLocation.name;
  const dates = getSelectedDates();
  const style = searchBudget.value;
  const styleWord = { cheap: 'budget-friendly', moderate: 'mid-range', expensive: 'luxury' }[style];
  const dateText = dates ? ` ${describeDates(dates)}` : '';

  let query;
  switch (searchExperience.value) {
    case 'hotels':
      query = `Find ${styleWord ? styleWord + ' ' : ''}hotels in ${where}${dates ? ` for a stay${dateText}` : ''}`;
      break;
    case 'restaurants':
      query = `Find ${styleWord ? styleWord + ' ' : ''}restaurants in ${where}`;
      break;
    case 'attractions':
      query = `What are the best ${style === 'cheap' ? 'free or low-cost ' : ''}attractions to visit in ${where}?`;
      break;
    case 'transport':
      query = `Show railway stations, bus stations and airports near ${where}`;
      break;
    default:
      query = dates
        ? `Plan a ${dates.days}-day ${styleWord ? styleWord + ' ' : ''}trip to ${where}${dateText}`
        : `Plan a 2-day ${styleWord ? styleWord + ' ' : ''}trip to ${where}`;
  }

  switchView('planner');
  handleUserSend(query, { explicit: true, dates });
}

function setupPromptCardsAndCapsule() {
  // Prompt cards on the landing page
  document.querySelectorAll('.prompt-card').forEach(card => {
    onActivate(card, () => {
      const template = card.getAttribute('data-prompt');
      if (!template) return;
      if (card.dataset.needsLocation === 'true' && !activeLocation) {
        nudgeLocationInput('Choose a destination first — type a city or tap 📍 for your current location.');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      switchView('planner');
      handleUserSend(fillPrompt(template), { explicit: Boolean(activeLocation) });
    });
  });

  // Photos that fail to load fall back to a gradient instead of a broken icon
  document.querySelectorAll('.prompt-card-media img').forEach(img => {
    const fallback = () => img.closest('.prompt-card-media').classList.add('is-fallback');
    if (img.complete && img.naturalWidth === 0) fallback();
    img.addEventListener('error', fallback);
  });

  // Shortcut chips in the planner
  document.querySelectorAll('.filter-chip[data-prompt], .quick-chip[data-prompt]').forEach(chip => {
    onActivate(chip, () => handleUserSend(fillPrompt(chip.getAttribute('data-prompt'))));
  });

  // Search bar
  btnCapsuleSearch.addEventListener('click', runCapsuleSearch);
  searchWhere.addEventListener('keydown', e => {
    // Enter with no suggestion to pick runs the search
    if (e.key === 'Enter' && !e.defaultPrevented) { e.preventDefault(); runCapsuleSearch(); }
  });
  [searchStart, searchEnd, searchExperience, searchBudget].forEach(el => {
    el.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); runCapsuleSearch(); } });
  });

  // Chat input
  btnChatSend.addEventListener('click', () => handleUserSend());
  chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      handleUserSend();
    }
  });
}


/* =====================================================================
   9. INITIALIZATION
   ===================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  setupNavigation();
  setupLocationControls();
  setupDateInputs();
  renderDestinations();
  setupPromptCardsAndCapsule();
  renderLocation();
  chatMessages.innerHTML = welcomeMessageHtml();
  checkBackendHealth();
  initLocation().then(() => {
    // refresh the welcome text once the location is known (if untouched)
    if (chatMessages.children.length === 1) chatMessages.innerHTML = welcomeMessageHtml();
  });
});
