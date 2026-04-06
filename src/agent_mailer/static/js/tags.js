// --- Tag editor ---
function refreshTagEditor() {
  const editor = document.getElementById('tagEditor');
  if (!editor) return;
  const agentId = currentView?.agentId;
  if (!agentId) return;
  const entry = statsData.find(a => a.agent_id === agentId);
  const tags = entry ? (entry.tags || []) : [];
  const pills = tags.map((t, i) =>
    `<span class="tag-pill">${esc(t)}<button class="tag-remove" data-tag-idx="${i}" onclick="event.stopPropagation(); removeTag(${i})">&times;</button></span>`
  ).join('');
  const inputVal = document.getElementById('tagInput')?.value || '';
  editor.innerHTML = `${pills}<div class="tag-input-wrap"><input class="tag-input" id="tagInput" type="text" placeholder="+ 添加标签" data-agent-id="${esc(agentId)}" autocomplete="off"><div class="tag-autocomplete" id="tagAutocomplete"></div></div>`;
  const newInput = document.getElementById('tagInput');
  if (newInput) {
    newInput.value = inputVal;
    hydrateTagInput();
  }
}

async function updateAgentTags(agentId, tags) {
  await api(`/admin/agents/${encodeURIComponent(agentId)}/tags`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tags }),
  });
  const entry = statsData.find(a => a.agent_id === agentId);
  if (entry) entry.tags = tags;
  await refreshSidebar();
}

async function removeTag(idx) {
  const agentId = currentView?.agentId;
  if (!agentId) return;
  const entry = statsData.find(a => a.agent_id === agentId);
  if (!entry) return;
  const tags = [...(entry.tags || [])];
  tags.splice(idx, 1);
  await updateAgentTags(agentId, tags);
  refreshTagEditor();
}

function getAllTags() {
  const s = new Set();
  statsData.forEach(a => (a.tags || []).forEach(t => s.add(t)));
  return [...s].sort();
}

function updateAutocomplete() {
  const input = document.getElementById('tagInput');
  const ac = document.getElementById('tagAutocomplete');
  if (!input || !ac) return;
  const val = input.value.trim().toLowerCase();
  const agentId = currentView?.agentId;
  const cur = agentId ? statsData.find(a => a.agent_id === agentId) : null;
  const curTags = cur ? (cur.tags || []) : [];
  const candidates = getAllTags().filter(t => !curTags.includes(t));
  const filtered = val ? candidates.filter(t => t.toLowerCase().includes(val)) : candidates;
  if (filtered.length === 0) { ac.classList.remove('visible'); ac.innerHTML = ''; return; }
  ac.innerHTML = filtered.map((t, i) =>
    `<div class="tag-ac-item${i === acIndex ? ' active' : ''}" data-tag="${esc(t)}">${acHighlight(t, val)}</div>`
  ).join('');
  ac.classList.add('visible');
}

function acHighlight(tag, q) {
  if (!q) return esc(tag);
  const idx = tag.toLowerCase().indexOf(q);
  if (idx < 0) return esc(tag);
  return esc(tag.substring(0, idx)) + '<strong>' + esc(tag.substring(idx, idx + q.length)) + '</strong>' + esc(tag.substring(idx + q.length));
}

function acHighlightItems(items) {
  items.forEach((it, i) => it.classList.toggle('active', i === acIndex));
  if (acIndex >= 0 && items[acIndex]) items[acIndex].scrollIntoView({ block: 'nearest' });
}

function hideAutocomplete() {
  const ac = document.getElementById('tagAutocomplete');
  if (ac) { ac.classList.remove('visible'); ac.innerHTML = ''; }
  acIndex = -1;
}

async function selectAutocompleteTag(tagValue) {
  const agentId = currentView?.agentId;
  if (!agentId) return;
  const entry = statsData.find(a => a.agent_id === agentId);
  if (!entry) return;
  const tags = [...(entry.tags || [])];
  if (!tags.includes(tagValue)) {
    tags.push(tagValue);
    await updateAgentTags(agentId, tags);
  }
  const input = document.getElementById('tagInput');
  if (input) input.value = '';
  acIndex = -1;
  refreshTagEditor();
}

function hydrateTagInput() {
  const input = document.getElementById('tagInput');
  const ac = document.getElementById('tagAutocomplete');
  if (!input) return;
  input.addEventListener('focus', () => {
    tagEditingActive = true;
    stopPolling();
    acIndex = -1;
    updateAutocomplete();
  });
  input.addEventListener('blur', () => {
    setTimeout(() => {
      hideAutocomplete();
      tagEditingActive = false;
      startPolling();
    }, 150);
  });
  input.addEventListener('input', () => {
    acIndex = -1;
    updateAutocomplete();
  });
  if (ac) {
    ac.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const item = e.target.closest('.tag-ac-item');
      if (item) selectAutocompleteTag(item.dataset.tag);
    });
  }
  input.addEventListener('keydown', async (e) => {
    const items = ac ? ac.querySelectorAll('.tag-ac-item') : [];
    const acVisible = ac && ac.classList.contains('visible');
    if (e.key === 'ArrowDown' && acVisible) {
      e.preventDefault();
      acIndex = Math.min(acIndex + 1, items.length - 1);
      acHighlightItems(items);
      return;
    }
    if (e.key === 'ArrowUp' && acVisible) {
      e.preventDefault();
      acIndex = Math.max(acIndex - 1, -1);
      acHighlightItems(items);
      return;
    }
    if (e.key === 'Escape') { hideAutocomplete(); return; }
    if (e.key !== 'Enter') return;
    e.preventDefault();
    let val;
    if (acVisible && acIndex >= 0 && items[acIndex]) {
      val = items[acIndex].dataset.tag;
    } else {
      val = input.value.trim();
    }
    if (!val) return;
    const agentId = currentView?.agentId;
    if (!agentId) return;
    const entry = statsData.find(a => a.agent_id === agentId);
    if (!entry) return;
    const tags = [...(entry.tags || [])];
    if (!tags.includes(val)) {
      tags.push(val);
      await updateAgentTags(agentId, tags);
    }
    input.value = '';
    acIndex = -1;
    refreshTagEditor();
  });
}

// --- Tag filter ---
function openFilterModal() {
  renderFilterModal();
  document.getElementById('filterModal').classList.add('visible');
}

function closeFilterModal() {
  document.getElementById('filterModal').classList.remove('visible');
}

function renderFilterModal() {
  const container = document.getElementById('filterModalTags');
  const allTags = getAllTags();
  if (allTags.length === 0) {
    container.innerHTML = '<div class="filter-modal-empty">暂无标签</div>';
    return;
  }
  container.innerHTML = allTags.map(t =>
    `<button class="filter-modal-tag${filterTags.has(t) ? ' selected' : ''}" data-tag="${esc(t)}" onclick="toggleFilterTag(this.dataset.tag)">${esc(t)}</button>`
  ).join('');
}

function toggleFilterTag(tag) {
  if (filterTags.has(tag)) filterTags.delete(tag);
  else filterTags.add(tag);
  renderFilterModal();
  updateFilterBtn();
  refreshSidebar();
  saveFilterTags();
}

function clearFilterTags() {
  filterTags.clear();
  renderFilterModal();
  updateFilterBtn();
  refreshSidebar();
  saveFilterTags();
  closeFilterModal();
}

function saveFilterTags() {
  api('/users/me/filter-tags', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filter_tags: [...filterTags] }),
  }).catch(() => {});
}

function updateFilterBtn() {
  const btn = document.getElementById('filterToggleBtn');
  if (!btn) return;
  const n = filterTags.size;
  btn.className = 'sidebar-filter-btn' + (n > 0 ? ' active' : '');
  btn.innerHTML = `<span class="filter-icon">&#9881;</span> 标签过滤${n > 0 ? ' (' + n + ')' : ''}`;
}

function updateFilterVisibility() {
  const row = document.getElementById('filterRow');
  if (sidebarMode === 'agents' && !document.getElementById('sidebarModeSelect').disabled) {
    row.style.display = '';
  } else {
    row.style.display = 'none';
  }
}
