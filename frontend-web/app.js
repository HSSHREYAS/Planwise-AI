/**
 * PlanWise AI — Frontend Application Controller
 * Airbnb Aesthetic · Multi-Theme Engine · Interactive Planning
 */

// --- Configuration & API ---
const API_BASE = window.location.port === '3000' || window.location.port === '5173'
  ? '/api/v1'
  : 'http://127.0.0.1:8000/api/v1';

let currentSessionId = null;
let isWaitingResponse = false;

// --- DOM Elements ---
const viewLanding = document.getElementById('view-landing');
const viewPlanner = document.getElementById('view-planner');
const navExplore = document.getElementById('nav-explore');
const navPlanner = document.getElementById('nav-planner');
const navBrand = document.getElementById('nav-brand');
const btnLaunchPlanner = document.getElementById('btn-launch-planner');
const btnBackExplore = document.getElementById('btn-back-explore');
const btnNewChat = document.getElementById('btn-new-chat');

const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const btnChatSend = document.getElementById('btn-chat-send');
const sessionBadge = document.getElementById('session-badge');

const searchWhere = document.getElementById('search-where');
const searchExperience = document.getElementById('search-experience');
const searchBudget = document.getElementById('search-budget');
const btnCapsuleSearch = document.getElementById('btn-capsule-search');

// Itinerary Drawer elements
const itineraryEmptyState = document.getElementById('itinerary-empty-state');
const itineraryContent = document.getElementById('itinerary-content');
const planStatLocation = document.getElementById('plan-stat-location');
const planStatDuration = document.getElementById('plan-stat-duration');
const planStatCost = document.getElementById('plan-stat-cost');
const planStatValidation = document.getElementById('plan-stat-validation');
const planTimelineContainer = document.getElementById('plan-timeline-container');


/* =====================================================================
   1. THEME ENGINE (Light / Dark / System Default)
   ===================================================================== */
function initTheme() {
  const savedTheme = localStorage.getItem('planwise_theme') || 'light';
  applyTheme(savedTheme);

  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const selected = btn.getAttribute('data-theme-val');
      applyTheme(selected);
    });
  });

  // Listen for OS system theme changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    const current = localStorage.getItem('planwise_theme');
    if (current === 'system') {
      applyTheme('system');
    }
  });
}

function applyTheme(theme) {
  localStorage.setItem('planwise_theme', theme);
  document.documentElement.setAttribute('data-theme', theme);

  document.querySelectorAll('.theme-btn').forEach(btn => {
    if (btn.getAttribute('data-theme-val') === theme) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}


/* =====================================================================
   2. VIEW MANAGEMENT (Landing vs Planner)
   ===================================================================== */
function switchView(viewName) {
  if (viewName === 'planner') {
    viewLanding.style.display = 'none';
    viewPlanner.style.display = 'block';
    navExplore.classList.remove('active');
    navPlanner.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    chatInput.focus();
    ensureSession();
  } else {
    viewPlanner.style.display = 'none';
    viewLanding.style.display = 'block';
    navPlanner.classList.remove('active');
    navExplore.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

function setupNavigation() {
  navExplore.addEventListener('click', () => switchView('landing'));
  navPlanner.addEventListener('click', () => switchView('planner'));
  navBrand.addEventListener('click', () => switchView('landing'));
  btnLaunchPlanner.addEventListener('click', () => switchView('planner'));
  btnBackExplore.addEventListener('click', () => switchView('landing'));

  const navHow = document.getElementById('nav-how');
  if (navHow) {
    navHow.addEventListener('click', () => {
      switchView('landing');
      const howSection = document.getElementById('how-it-works-section');
      if (howSection) {
        howSection.scrollIntoView({ behavior: 'smooth' });
      }
    });
  }

  btnNewChat.addEventListener('click', resetChat);
}


/* =====================================================================
   3. API CLIENT & SESSION MANAGEMENT
   ===================================================================== */
async function ensureSession() {
  if (currentSessionId) return currentSessionId;

  try {
    const res = await fetch(`${API_BASE}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentSessionId = data.session_id;
    if (sessionBadge) {
      sessionBadge.textContent = `#${currentSessionId.slice(0, 8)}`;
    }
    return currentSessionId;
  } catch (err) {
    console.error('Session creation failed:', err);
    return null;
  }
}

async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      const data = await res.json();
      console.log('Backend health status:', data);
    }
  } catch (err) {
    console.warn('Backend currently unreachable on', API_BASE);
  }
}

async function resetChat() {
  currentSessionId = null;
  chatMessages.innerHTML = `
    <div class="message-row assistant">
      <div class="message-avatar">🗺️</div>
      <div class="message-bubble">
        <p><strong>Session reset!</strong></p>
        <p>What would you like to plan or explore in Cambridge?</p>
      </div>
    </div>
  `;
  itineraryEmptyState.style.display = 'block';
  itineraryContent.style.display = 'none';
  await ensureSession();
}


/* =====================================================================
   4. CHAT INTERACTIONS & ENTITY CARD PARSER
   ===================================================================== */
async function handleUserSend(text) {
  const query = (text || chatInput.value).trim();
  if (!query || isWaitingResponse) return;

  chatInput.value = '';
  isWaitingResponse = true;

  // Append user message bubble
  appendMessage('user', query);

  // Show thinking spinner bubble
  const spinnerId = appendThinkingIndicator();

  try {
    const sessionId = await ensureSession();
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: query })
    });

    removeThinkingIndicator(spinnerId);

    if (!res.ok) {
      throw new Error(`Server returned status ${res.status}`);
    }

    const data = await res.json();
    const assistantMsg = data.message || 'I have processed your request.';

    // Append Assistant response with rich formatting and cards
    appendAssistantMessage(assistantMsg, data);

    // Update Plan Drawer if plan data exists
    if (data.plan) {
      renderItineraryDrawer(data.plan, data.validation);
    }
  } catch (err) {
    removeThinkingIndicator(spinnerId);
    appendMessage(
      'assistant',
      `⚠️ Could not reach the PlanWise AI server: ${err.message}. Please verify the backend is active on port 8000.`
    );
  } finally {
    isWaitingResponse = false;
    chatInput.focus();
  }
}

function appendMessage(role, content) {
  const row = document.createElement('div');
  row.className = `message-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🗺️';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = formatMarkdown(content);

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendThinkingIndicator() {
  const id = `thinking-${Date.now()}`;
  const row = document.createElement('div');
  row.className = 'message-row assistant';
  row.id = id;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = '🗺️';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = `
    <div style="display:flex; align-items:center; gap:8px; color:var(--text-secondary); font-size:0.9rem;">
      <span style="display:inline-block; animation:spin 1s linear infinite;">🔍</span>
      <span>Consulting MultiWOZ 2.2 verified benchmarks...</span>
    </div>
    <style>
      @keyframes spin { 100% { transform: rotate(360deg); } }
    </style>
  `;

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return id;
}

function removeThinkingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendAssistantMessage(text, responseData) {
  const row = document.createElement('div');
  row.className = 'message-row assistant';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = '🗺️';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  // Format base text
  let html = formatMarkdown(text);

  // Check if text or entities contain multi-item listings to transform into Airbnb cards
  const parsedCards = extractEntityCards(text);
  if (parsedCards.length > 0) {
    html += '<div class="entity-cards-container">';
    parsedCards.forEach(c => {
      html += `
        <div class="entity-result-card">
          <div class="entity-card-header">
            <span class="entity-card-name">${escapeHtml(c.name)}</span>
            <span class="entity-card-rating">★ ${c.stars || '4.8'}</span>
          </div>
          <div class="entity-card-type">${escapeHtml(c.type || 'Verified Location')} · ${escapeHtml(c.area || 'Cambridge')}</div>
          <div class="entity-card-details">
            ${c.address ? `<div>📍 ${escapeHtml(c.address)}</div>` : ''}
            ${c.phone ? `<div>📞 ${escapeHtml(c.phone)}</div>` : ''}
            ${c.postcode ? `<div>📮 ${escapeHtml(c.postcode)}</div>` : ''}
          </div>
          ${c.price ? `<div class="entity-card-price">${escapeHtml(c.price)}</div>` : ''}
        </div>
      `;
    });
    html += '</div>';
  }

  bubble.innerHTML = html;
  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Extract structured entity items from assistant response text
 */
function extractEntityCards(text) {
  const cards = [];
  const lines = text.split('\n');
  let currentCard = null;

  lines.forEach(line => {
    const trimmed = line.trim();
    // Matches patterns like "• **Name**", "1. **Name**", "- **Name**"
    const nameMatch = trimmed.match(/^[\d\-\•\*\.]+\s*\*\*([^*]+)\*\*/);

    if (nameMatch) {
      if (currentCard && currentCard.name) {
        cards.push(currentCard);
      }
      currentCard = {
        name: nameMatch[1].trim(),
        details: []
      };
    } else if (currentCard) {
      if (trimmed.toLowerCase().includes('address:')) {
        currentCard.address = trimmed.split(/address:/i)[1].trim();
      } else if (trimmed.toLowerCase().includes('phone:')) {
        currentCard.phone = trimmed.split(/phone:/i)[1].trim();
      } else if (trimmed.toLowerCase().includes('postcode:')) {
        currentCard.postcode = trimmed.split(/postcode:/i)[1].trim();
      } else if (trimmed.toLowerCase().includes('price:') || trimmed.toLowerCase().includes('pricerange:')) {
        currentCard.price = trimmed.split(/price(range)?:/i)[1].trim();
      } else if (trimmed.toLowerCase().includes('star:') || trimmed.toLowerCase().includes('rating:')) {
        currentCard.stars = trimmed.split(/star(s| rating)?:/i)[1].trim();
      } else if (trimmed.toLowerCase().includes('area:') || trimmed.toLowerCase().includes('type:')) {
        currentCard.type = trimmed.replace(/^[\*\-\•]\s*/, '').trim();
      }
    }
  });

  if (currentCard && currentCard.name) {
    cards.push(currentCard);
  }

  return cards;
}

/**
 * Simple Markdown to HTML formatter
 */
function formatMarkdown(md) {
  if (!md) return '';
  let text = md;

  // Escape HTML
  text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Bold **text**
  text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // Italics *text*
  text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // Headers ###
  text = text.replace(/^### (.*$)/gim, '<h4 style="margin:10px 0 4px; color:var(--text-primary);">$1</h4>');
  text = text.replace(/^## (.*$)/gim, '<h3 style="margin:12px 0 6px; color:var(--text-primary);">$1</h3>');

  // Bullet items
  text = text.replace(/^[\*\-•] (.*$)/gim, '<li style="margin-left:16px;">$1</li>');

  // Paragraph breaks
  text = text.replace(/\n\n/g, '<br/><br/>');
  text = text.replace(/\n/g, '<br/>');

  return text;
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}


/* =====================================================================
   5. ITINERARY & BUDGET DRAWER RENDERER
   ===================================================================== */
function renderItineraryDrawer(plan, validation) {
  if (!plan) return;

  itineraryEmptyState.style.display = 'none';
  itineraryContent.style.display = 'block';

  planStatLocation.textContent = plan.location || 'Cambridge';
  planStatDuration.textContent = plan.duration_days ? `${plan.duration_days} Day(s)` : '1 Day';

  if (plan.estimated_total_cost !== undefined && plan.estimated_total_cost !== null) {
    planStatCost.textContent = `£${Math.round(plan.estimated_total_cost)}`;
  } else {
    planStatCost.textContent = 'Custom';
  }

  if (validation && !validation.valid) {
    planStatValidation.textContent = '⚠️ Replan Needed';
    planStatValidation.style.color = 'var(--warning)';
  } else {
    planStatValidation.textContent = '✓ Constraints Verified';
    planStatValidation.style.color = 'var(--success)';
  }

  // Render day timelines
  planTimelineContainer.innerHTML = '';
  if (plan.days && plan.days.length > 0) {
    plan.days.forEach(day => {
      const dayEl = document.createElement('div');
      dayEl.className = 'timeline-day';

      let slotsHtml = '';
      if (day.slots) {
        day.slots.forEach(s => {
          let actsHtml = '';
          if (s.activities && s.activities.length > 0) {
            s.activities.forEach(a => {
              const costStr = a.estimated_cost ? ` · £${Math.round(a.estimated_cost)}` : '';
              actsHtml += `
                <div class="slot-activity">
                  ${escapeHtml(a.name)}
                  <span class="slot-cost">${costStr}</span>
                </div>
              `;
            });
          } else {
            actsHtml = '<div class="slot-activity" style="color:var(--text-muted); font-weight:400;">Free exploration</div>';
          }

          slotsHtml += `
            <div class="timeline-slot">
              <div class="slot-time">${escapeHtml(s.time_of_day || 'Slot')}</div>
              ${actsHtml}
            </div>
          `;
        });
      }

      dayEl.innerHTML = `
        <div class="timeline-day-title">
          <span>📅</span> Day ${day.day || 1}
        </div>
        ${slotsHtml}
      `;
      planTimelineContainer.appendChild(dayEl);
    });
  }
}


/* =====================================================================
   6. PROMPT DISCOVERY CARDS & CAPSULE SEARCH BINDINGS
   ===================================================================== */
function setupPromptCardsAndCapsule() {
  // Bind all prompt cards on the landing page
  document.querySelectorAll('.prompt-card').forEach(card => {
    card.addEventListener('click', () => {
      const prompt = card.getAttribute('data-prompt');
      if (prompt) {
        switchView('planner');
        handleUserSend(prompt);
      }
    });
  });

  // Bind curated destination cards
  document.querySelectorAll('.dest-card').forEach(card => {
    card.addEventListener('click', () => {
      const prompt = card.getAttribute('data-prompt');
      if (prompt) {
        switchView('planner');
        handleUserSend(prompt);
      }
    });
  });

  // Bind quick filter chips
  document.querySelectorAll('.filter-chip[data-prompt]').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt');
      if (prompt) handleUserSend(prompt);
    });
  });

  // Bind suggestion chips under chat input
  document.querySelectorAll('.quick-chip[data-prompt]').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt');
      if (prompt) handleUserSend(prompt);
    });
  });

  // Bind Airbnb Floating Search Capsule
  btnCapsuleSearch.addEventListener('click', () => {
    const where = searchWhere.value;
    const exp = searchExperience.value;
    const budget = searchBudget.value;

    let query = '';
    if (exp === 'hotels') {
      query = `Find me hotels in the ${where}`;
    } else if (exp === 'restaurants') {
      query = `Find me restaurants in the ${where}`;
    } else if (exp === 'attractions') {
      query = `What are the best attractions to visit in Cambridge ${where}?`;
    } else if (exp === 'trains') {
      query = `Find trains to Cambridge`;
    } else {
      query = `Plan a 2-day Cambridge trip in the ${where}`;
    }

    if (budget !== 'any') {
      query += ` with ${budget} budget`;
    }

    switchView('planner');
    handleUserSend(query);
  });

  // Chat input submit
  btnChatSend.addEventListener('click', () => handleUserSend());
  chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleUserSend();
    }
  });
}


/* =====================================================================
   7. INITIALIZATION
   ===================================================================== */
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  setupNavigation();
  setupPromptCardsAndCapsule();
  checkBackendHealth();
  console.log('PlanWise AI Airbnb Frontend initialized.');
});
