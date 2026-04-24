// --- Teams management ---

let teamsData = [];

async function fetchTeams() {
  teamsData = await api('/admin/teams');
  return teamsData;
}

async function fetchTeamDetail(teamId) {
  return api(`/admin/teams/${encodeURIComponent(teamId)}`);
}

async function showTeams() {
  clearNav();
  setSidebarSpecialMode('none');
  document.getElementById('navTeams').classList.add('active');
  currentView = { type: 'teams' };
  await renderTeams();
}

async function renderTeams() {
  if (currentView?.type !== 'teams' && currentView?.type !== 'teamDetail') return;
  const main = document.getElementById('main');

  if (currentView?.type === 'teamDetail') {
    await renderTeamDetail(currentView.teamId);
    return;
  }

  await fetchTeams();

  const teamsHtml = teamsData.length === 0
    ? `<div class="empty" style="padding:32px 0;text-align:center">
        <p>${esc(t('teams.empty'))}</p>
        <p class="team-empty-hint">${esc(t('teams.emptyHint'))}</p>
        <button class="btn btn-primary" onclick="showCreateTeamForm()">${esc(t('teams.createFirst'))}</button>
      </div>`
    : `<div class="teams-grid">${teamsData.map(tm => `
        <div class="team-card" onclick="showTeamDetail('${esc(tm.id)}')">
          <div class="team-card-icon">${tm.agent_count > 0
            ? `<span class="team-card-avatar-count">${tm.agent_count}</span>`
            : '<span class="team-card-avatar-empty">0</span>'}</div>
          <div class="team-card-name">${esc(tm.name)}</div>
          <div class="team-card-desc">${esc(tm.description) || `<span class="text-muted">${esc(t('teams.noDescription'))}</span>`}</div>
          <div class="team-card-footer">
            <span class="team-agent-count">${tm.agent_count} ${esc(t('teams.agents'))}</span>
            <span class="team-card-time">${esc(fmtTime(tm.created_at))}</span>
          </div>
        </div>
      `).join('')}</div>`;

  main.innerHTML = `
    <div class="card">
      <div class="card-header-row">
        <h2>${esc(t('teams.title'))}</h2>
        ${teamsData.length > 0 ? `<button class="btn btn-primary" onclick="showCreateTeamForm()">${esc(t('teams.create'))}</button>` : ''}
      </div>
      ${teamsHtml}
    </div>`;
}

function showCreateTeamForm() {
  currentView = { type: 'teamCreate' };
  const main = document.getElementById('main');
  main.innerHTML = `
    <div class="card">
      <button type="button" class="back-btn" onclick="showTeams()">${esc(t('teams.backList'))}</button>
      <h2>${esc(t('teams.createTitle'))}</h2>
      <div class="compose-form">
        <div>
          <label for="teamName">${esc(t('teams.name'))}</label>
          <input type="text" id="teamName" placeholder="${esc(t('teams.namePlaceholder'))}">
        </div>
        <div>
          <label for="teamDesc">${esc(t('teams.description'))}</label>
          <input type="text" id="teamDesc" placeholder="${esc(t('teams.descPlaceholder'))}">
        </div>
        <div id="teamFormError" class="login-error" style="display:none"></div>
        <div>
          <button class="btn btn-primary" id="createTeamBtn" onclick="doCreateTeam()">${esc(t('teams.createBtn'))}</button>
        </div>
      </div>
    </div>`;
}

async function doCreateTeam() {
  const name = document.getElementById('teamName').value.trim();
  const description = document.getElementById('teamDesc').value.trim();
  const errEl = document.getElementById('teamFormError');
  if (!name) {
    errEl.textContent = t('teams.nameRequired');
    errEl.style.display = 'block';
    return;
  }
  try {
    await api('/admin/teams', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description }),
    });
    await showTeams();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

async function showTeamDetail(teamId) {
  clearNav();
  document.getElementById('navTeams').classList.add('active');
  currentView = { type: 'teamDetail', teamId };
  await renderTeamDetail(teamId);
}

async function renderTeamDetail(teamId) {
  const main = document.getElementById('main');
  let team;
  try {
    team = await fetchTeamDetail(teamId);
  } catch (e) {
    main.innerHTML = `<div class="card">
      <button type="button" class="back-btn" onclick="showTeams()">${esc(t('teams.backList'))}</button>
      <p class="empty">${esc(t('teams.notFound'))}</p></div>`;
    return;
  }

  // Fetch all agents to find unassigned ones
  const allAgents = await api('/admin/agents');
  const unassigned = allAgents.filter(a => !a.team_id && a.role !== 'operator');

  // Members table
  const membersHtml = team.agents.length === 0
    ? `<div class="empty" style="padding:16px 0">${esc(t('teams.membersEmpty'))}</div>`
    : `<div class="stats-table-wrap">
        <table class="stats-table">
          <thead>
            <tr>
              <th>${esc(t('teams.colName'))}</th>
              <th>${esc(t('teams.colRole'))}</th>
              <th>${esc(t('teams.colAddress'))}</th>
              <th>${esc(t('teams.colStatus'))}</th>
              <th>${esc(t('teams.colAction'))}</th>
            </tr>
          </thead>
          <tbody>
            ${team.agents.map(a => `
              <tr>
                <td><strong>${esc(a.name)}</strong></td>
                <td>${esc(a.role)}</td>
                <td class="text-muted">${esc(a.address)}</td>
                <td><span class="status-dot status-${a.status || 'offline'}" title="${esc(_statusTitle(a.status))}"></span> ${esc(a.status || 'offline')}</td>
                <td><button class="btn-danger-sm" onclick="removeAgentFromTeam('${esc(team.id)}', '${esc(a.id)}', '${esc(a.name)}')">${esc(t('teams.remove'))}</button></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;

  // Add agent section
  let addAgentHtml;
  if (unassigned.length === 0) {
    addAgentHtml = `<div class="empty" style="padding:12px 0;font-size:12px">${esc(t('teams.allAssigned'))}</div>`;
  } else {
    addAgentHtml = `
      <p class="team-section-hint">${esc(t('teams.addMemberHint'))}</p>
      <div class="compose-form">
        <div>
          <label for="addAgentSelect">${esc(t('teams.addMemberLabel'))}</label>
          <select id="addAgentSelect">
            <option value="">${esc(t('teams.addMemberSelect'))}</option>
            ${unassigned.map(a => `<option value="${esc(a.id)}">${esc(a.name)} (${esc(a.role)}) — ${esc(a.address)}</option>`).join('')}
          </select>
        </div>
        <div>
          <button class="btn btn-primary" onclick="addAgentToTeam('${esc(team.id)}')">${esc(t('teams.addMemberBtn'))}</button>
        </div>
      </div>`;
  }

  // Fetch memories
  let memories = [];
  try {
    memories = await fetchTeamMemories(teamId);
  } catch (e) { /* ignore */ }

  const memoriesListHtml = memories.length === 0
    ? `<div class="empty" style="padding:12px 0">${esc(t('teams.noMemories'))}</div>`
    : memories.map(m => `
        <div class="memory-item" id="memory-${esc(m.id)}">
          <div class="memory-item-header" onclick="toggleMemoryEdit('${esc(teamId)}', '${esc(m.id)}')">
            <div class="memory-item-title">${esc(m.title)}</div>
            <div class="memory-item-meta">
              <span class="text-muted">${esc(fmtTime(m.updated_at))}</span>
              <button class="memory-copy-btn" onclick="event.stopPropagation(); copyMemoryUrl('${esc(m.id)}')" title="${esc(t('teams.copyUrl'))}">${esc(t('teams.copyUrl'))}</button>
              <button class="btn-danger-sm" onclick="event.stopPropagation(); doDeleteMemory('${esc(teamId)}', '${esc(m.id)}', '${esc(m.title)}')">${esc(t('teams.delete'))}</button>
            </div>
          </div>
          <div class="memory-edit-form" id="memoryEdit-${esc(m.id)}" style="display:none">
            <div>
              <label>${esc(t('teams.memoryTitle'))}</label>
              <input type="text" id="memoryTitle-${esc(m.id)}" value="${esc(m.title)}" maxlength="100">
            </div>
            <div>
              <label>${esc(t('teams.memoryContent'))} <span class="memory-char-count" id="memoryCount-${esc(m.id)}">${(m.content || '').length}/200000</span></label>
              <textarea id="memoryContent-${esc(m.id)}" maxlength="200000" oninput="updateMemoryCharCount('${esc(m.id)}')">${esc(m.content)}</textarea>
            </div>
            <div class="memory-url-row">
              <span class="text-muted" style="font-size:11px">URL: ${location.origin}/memories/${esc(m.id)}</span>
            </div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-primary" onclick="doUpdateMemory('${esc(teamId)}', '${esc(m.id)}')">${esc(t('common.save'))}</button>
              <button class="btn btn-secondary" onclick="toggleMemoryEdit('${esc(teamId)}', '${esc(m.id)}')">${esc(t('common.cancel'))}</button>
            </div>
            <div class="login-error" id="memoryEditError-${esc(m.id)}" style="display:none"></div>
          </div>
        </div>
      `).join('');

  const addMemoryBtnHtml = `<button class="btn btn-primary" onclick="toggleAddMemoryForm()" id="addMemoryBtn">${esc(t('teams.addMemory'))}</button>`;

  const addMemoryFormHtml = `
    <div id="addMemoryForm" style="display:none">
      <div class="compose-form">
        <div>
          <label for="newMemoryTitle">${esc(t('teams.memoryTitle'))}</label>
          <input type="text" id="newMemoryTitle" placeholder="${esc(t('teams.memoryTitlePlaceholder'))}" maxlength="100">
        </div>
        <div>
          <label for="newMemoryContent">${esc(t('teams.memoryContent'))} <span class="memory-char-count" id="newMemoryCount">0/200000</span></label>
          <textarea id="newMemoryContent" placeholder="${esc(t('teams.memoryContentPlaceholder'))}" maxlength="200000" oninput="updateNewMemoryCharCount()"></textarea>
        </div>
        <div id="addMemoryError" class="login-error" style="display:none"></div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="doCreateMemory('${esc(teamId)}')">${esc(t('common.create'))}</button>
          <button class="btn btn-secondary" onclick="toggleAddMemoryForm()">${esc(t('common.cancel'))}</button>
        </div>
      </div>
    </div>`;

  main.innerHTML = `
    <div class="card">
      <button type="button" class="back-btn" onclick="showTeams()">${esc(t('teams.backList'))}</button>
      <div class="card-header-row">
        <div>
          <h2>${esc(team.name)}</h2>
          <p class="team-detail-desc">${esc(team.description) || `<span class="text-muted">${esc(t('teams.noDescription'))}</span>`}</p>
        </div>
        <div class="team-detail-actions">
          <button class="btn btn-secondary" onclick="showEditTeamForm('${esc(team.id)}')">${esc(t('common.edit'))}</button>
          <button class="btn btn-danger" onclick="deleteTeam('${esc(team.id)}', '${esc(team.name)}')">${esc(t('teams.delete'))}</button>
        </div>
      </div>
      <h3 class="team-section-header">${esc(t('teams.membersCount', { n: team.agents.length }))}</h3>
      ${membersHtml}
      <h3 class="team-section-header">${esc(t('teams.addMember'))}</h3>
      ${addAgentHtml}
      <h3 class="team-section-header">${esc(t('teams.sharedMemoriesCount', { n: memories.length }))}</h3>
      ${memoriesListHtml}
      ${addMemoryBtnHtml}
      ${addMemoryFormHtml}
    </div>`;
}

async function showEditTeamForm(teamId) {
  currentView = { type: 'teamEdit', teamId };
  let team;
  try {
    team = await fetchTeamDetail(teamId);
  } catch { return; }

  const main = document.getElementById('main');
  main.innerHTML = `
    <div class="card">
      <button type="button" class="back-btn" onclick="showTeamDetail('${esc(teamId)}')">${esc(t('common.back'))}</button>
      <h2>${esc(t('teams.editTitle'))}</h2>
      <div class="compose-form">
        <div>
          <label for="editTeamName">${esc(t('teams.name'))}</label>
          <input type="text" id="editTeamName" value="${esc(team.name)}">
        </div>
        <div>
          <label for="editTeamDesc">${esc(t('teams.description'))}</label>
          <input type="text" id="editTeamDesc" value="${esc(team.description)}" placeholder="${esc(t('teams.descPlaceholder'))}">
        </div>
        <div id="editTeamError" class="login-error" style="display:none"></div>
        <div>
          <button class="btn btn-primary" onclick="doUpdateTeam('${esc(teamId)}')">${esc(t('teams.saveChanges'))}</button>
        </div>
      </div>
    </div>`;
}

async function doUpdateTeam(teamId) {
  const name = document.getElementById('editTeamName').value.trim();
  const description = document.getElementById('editTeamDesc').value.trim();
  const errEl = document.getElementById('editTeamError');
  if (!name) {
    errEl.textContent = t('teams.nameRequired');
    errEl.style.display = 'block';
    return;
  }
  try {
    await api(`/admin/teams/${encodeURIComponent(teamId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description }),
    });
    await showTeamDetail(teamId);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

async function deleteTeam(teamId, teamName) {
  if (!await showConfirm(t('teams.confirmDeleteTitle'), t('teams.confirmDelete', { name: teamName }), t('common.delete'))) return;
  try {
    await api(`/admin/teams/${encodeURIComponent(teamId)}`, { method: 'DELETE' });
    await showTeams();
  } catch (e) {
    alert(e.message);
  }
}

async function addAgentToTeam(teamId) {
  const select = document.getElementById('addAgentSelect');
  const agentId = select.value;
  if (!agentId) return;
  try {
    await api(`/admin/teams/${encodeURIComponent(teamId)}/agents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId }),
    });
    await renderTeamDetail(teamId);
  } catch (e) {
    alert(e.message);
  }
}

async function removeAgentFromTeam(teamId, agentId, agentName) {
  if (!await showConfirm(t('teams.confirmRemoveTitle'), t('teams.confirmRemove', { name: agentName }), t('teams.remove'))) return;
  try {
    await api(`/admin/teams/${encodeURIComponent(teamId)}/agents/${encodeURIComponent(agentId)}`, {
      method: 'DELETE',
    });
    await renderTeamDetail(teamId);
  } catch (e) {
    alert(e.message);
  }
}

// --- Team Memories UI ---

function toggleAddMemoryForm() {
  const form = document.getElementById('addMemoryForm');
  const btn = document.getElementById('addMemoryBtn');
  if (form.style.display === 'none') {
    form.style.display = 'block';
    if (btn) btn.style.display = 'none';
    document.getElementById('newMemoryTitle').focus();
  } else {
    form.style.display = 'none';
    if (btn) btn.style.display = '';
  }
}

function toggleMemoryEdit(teamId, memoryId) {
  const form = document.getElementById('memoryEdit-' + memoryId);
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

function updateMemoryCharCount(memoryId) {
  const ta = document.getElementById('memoryContent-' + memoryId);
  const counter = document.getElementById('memoryCount-' + memoryId);
  if (ta && counter) counter.textContent = ta.value.length + '/200000';
}

function updateNewMemoryCharCount() {
  const ta = document.getElementById('newMemoryContent');
  const counter = document.getElementById('newMemoryCount');
  if (ta && counter) counter.textContent = ta.value.length + '/200000';
}

async function doCreateMemory(teamId) {
  const title = document.getElementById('newMemoryTitle').value.trim();
  const content = document.getElementById('newMemoryContent').value;
  const errEl = document.getElementById('addMemoryError');
  if (!title) {
    errEl.textContent = t('teams.memoryTitleRequired');
    errEl.style.display = 'block';
    return;
  }
  try {
    await createTeamMemory(teamId, { title, content });
    await renderTeamDetail(teamId);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

async function doUpdateMemory(teamId, memoryId) {
  const title = document.getElementById('memoryTitle-' + memoryId).value.trim();
  const content = document.getElementById('memoryContent-' + memoryId).value;
  const errEl = document.getElementById('memoryEditError-' + memoryId);
  if (!title) {
    errEl.textContent = t('teams.memoryTitleRequired');
    errEl.style.display = 'block';
    return;
  }
  try {
    await updateTeamMemory(teamId, memoryId, { title, content });
    await renderTeamDetail(teamId);
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = 'block';
  }
}

async function doDeleteMemory(teamId, memoryId, title) {
  if (!await showConfirm(t('teams.confirmDeleteMemoryTitle'), t('teams.confirmDeleteMemory', { title }), t('common.delete'))) return;
  try {
    await deleteTeamMemory(teamId, memoryId);
    await renderTeamDetail(teamId);
  } catch (e) {
    alert(e.message);
  }
}

function copyMemoryUrl(memoryId) {
  const url = location.origin + '/memories/' + memoryId;
  navigator.clipboard.writeText(url).then(() => {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = t('teams.copied');
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });
}
