// --- Sidebar ---

function _statusTitle(status) {
  if (status === 'online') return t('sidebar.statusOnline');
  if (status === 'idle') return t('sidebar.statusIdle');
  return t('sidebar.statusOffline');
}

function _renderSidebarAgent(a, activeAddr, indented) {
  const indent = indented ? ' sidebar-agent-indented' : '';
  return `
    <div class="agent-item${indent} ${a.address === activeAddr ? 'active' : ''}"
         onclick='showInbox(${JSON.stringify(a.address)}, ${JSON.stringify(a.agent_id || a.id)})'>
      <div class="agent-info">
        <div class="agent-name"><span class="status-dot status-${a.status || 'offline'}" title="${esc(_statusTitle(a.status))}"></span>${esc(a.name)}</div>
        <div class="agent-role">${esc(a.role)} &middot; ${esc(a.address)}</div>
      </div>
      <span class="badge ${(a.messages_unread || 0) === 0 ? 'zero' : ''}">${a.messages_unread || 0}</span>
    </div>`;
}

/** @param {'none'|'archive'|'trash'} mode */
function setSidebarSpecialMode(mode) {
  const sel = document.getElementById('sidebarModeSelect');
  const lab = document.getElementById('sidebarModeLabel');
  if (!sel || !lab) return;
  if (mode === 'none') {
    sel.disabled = false;
    lab.textContent = t('sidebar.label');
  } else {
    sel.disabled = true;
    lab.textContent = mode === 'archive' ? t('sidebar.archive') : t('sidebar.trash');
  }
  updateFilterVisibility();
}

async function refreshSidebar() {
  const list = document.getElementById('agentList');
  const sel = document.getElementById('sidebarModeSelect');
  const sidebarInSpecialMode = sel && sel.disabled;
  const inTrashContext = sidebarInSpecialMode && (
    currentView?.type === 'trash' ||
    currentView?.type === 'trashedMessage' ||
    (currentView?.type === 'thread' && currentView.fromTrash));
  const inArchiveContext = sidebarInSpecialMode && (
    currentView?.type === 'archive' ||
    (currentView?.type === 'thread' && currentView.fromArchive));

  const noSubj = t('sidebar.noSubject');
  const msgSuffix = t('sidebar.msgCountSuffix');

  if (inTrashContext) {
    await fetchThreadsSummary({ trashed: true });
    await fetchTrashedMessages();
    const activeTid = currentView?.type === 'thread' ? currentView.threadId : null;
    const activeMid = currentView?.type === 'trashedMessage' ? currentView.messageId : null;
    if (threadsData.length === 0 && trashedMessagesData.length === 0) {
      list.innerHTML = `<div class="empty" style="padding:20px 16px;font-size:12px">${esc(t('sidebar.emptyTrash'))}</div>`;
      return;
    }
    const threadsBlock = threadsData.length === 0
      ? `<div class="empty" style="padding:8px 16px 12px;font-size:12px">${esc(t('sidebar.emptyNoThreadsTrash'))}</div>`
      : threadsData.map(th => `
    <div class="agent-item thread-sidebar-item ${th.thread_id === activeTid ? 'active' : ''}"
         data-thread-id="${th.thread_id}"
         onclick="showThreadFromSidebar(this.dataset.threadId, 'trash')">
      <div class="agent-info">
        <div class="agent-name">${esc(th.preview_subject) || esc(noSubj)}</div>
        <div class="agent-role">${esc(th.thread_id.substring(0, 8))}&hellip; &middot; ${th.message_count} ${esc(msgSuffix)}</div>
      </div>
      <span class="badge ${th.unread_count === 0 ? 'zero' : ''}">${th.unread_count}</span>
    </div>
  `).join('');
    const msgsBlock = trashedMessagesData.length === 0
      ? `<div class="empty" style="padding:8px 16px 12px;font-size:12px">${esc(t('sidebar.emptyNoMessagesTrash'))}</div>`
      : trashedMessagesData.map(tm => `
    <div class="agent-item thread-sidebar-item trash-msg-item ${tm.message_id === activeMid ? 'active' : ''}"
         data-message-id="${tm.message_id}"
         onclick="showTrashedMessageFromTrash(this.dataset.messageId)">
      <div class="agent-info">
        <div class="agent-name">${esc(tm.subject) || esc(noSubj)}</div>
        <div class="agent-role">${esc(tm.from_agent)} &middot; ${esc(tm.thread_id.substring(0, 8))}&hellip;</div>
      </div>
    </div>
  `).join('');
    list.innerHTML =
      `<div class="trash-split-title">${esc(t('sidebar.threadsDeleted'))}</div>` +
      threadsBlock +
      `<div class="trash-split-title">${esc(t('sidebar.messagesDeleted'))}</div>` +
      msgsBlock;
    return;
  }

  if (inArchiveContext) {
    await fetchThreadsSummary({ archived: true });
    const activeTid = currentView?.type === 'thread' ? currentView.threadId : null;
    list.innerHTML = threadsData.length === 0
      ? `<div class="empty" style="padding:20px 16px;font-size:12px">${esc(t('sidebar.emptyArchive'))}</div>`
      : threadsData.map(th => `
    <div class="agent-item thread-sidebar-item ${th.thread_id === activeTid ? 'active' : ''}"
         data-thread-id="${th.thread_id}"
         onclick="showThreadFromSidebar(this.dataset.threadId, 'archive')">
      <div class="agent-info">
        <div class="agent-name">${esc(th.preview_subject) || esc(noSubj)}</div>
        <div class="agent-role">${esc(th.thread_id.substring(0, 8))}&hellip; &middot; ${th.message_count} ${esc(msgSuffix)}</div>
      </div>
      <span class="badge ${th.unread_count === 0 ? 'zero' : ''}">${th.unread_count}</span>
    </div>
  `).join('');
    return;
  }

  if (sidebarMode === 'threads') {
    updateFilterVisibility();
    await fetchThreadsSummary({});
    const activeTid = currentView?.type === 'thread' ? currentView.threadId : null;
    list.innerHTML = threadsData.length === 0
      ? `<div class="empty" style="padding:20px 16px;font-size:12px">${esc(t('sidebar.emptyThreads'))}</div>`
      : threadsData.map(th => `
    <div class="agent-item thread-sidebar-item ${th.thread_id === activeTid ? 'active' : ''}"
         data-thread-id="${th.thread_id}"
         onclick="showThreadFromSidebar(this.dataset.threadId, null)">
      <div class="agent-info">
        <div class="agent-name">${esc(th.preview_subject) || esc(noSubj)}</div>
        <div class="agent-role">${esc(th.thread_id.substring(0, 8))}&hellip; &middot; ${th.message_count} ${esc(msgSuffix)}</div>
      </div>
      <span class="badge ${th.unread_count === 0 ? 'zero' : ''}">${th.unread_count}</span>
    </div>
  `).join('');
    return;
  }

  if (sidebarMode === 'teams') {
    updateFilterVisibility();
    await fetchStats();
    await fetchTeams();
    // Fetch team details for member lists
    const teamDetails = [];
    for (const tm of teamsData) {
      try { teamDetails.push(await fetchTeamDetail(tm.id)); } catch {}
    }
    const agentsList = await fetchAgents();
    const activeAddr = currentView?.type === 'inbox' ? currentView.address : null;

    // Build stats lookup for unread counts
    const statsMap = {};
    for (const s of statsData) statsMap[s.address] = s;

    // Human operator first
    const opAgent = statsData.find(a => a.address === HUMAN_OPERATOR_ADDRESS);
    let html = '';
    if (opAgent) {
      html += _renderSidebarAgent(opAgent, activeAddr);
    }

    // Render each team
    for (const team of teamDetails) {
      const collapsed = document.querySelector(`.sidebar-team-group[data-team-id="${team.id}"]`)?.classList.contains('collapsed') || false;
      html += `<div class="sidebar-team-group${collapsed ? ' collapsed' : ''}" data-team-id="${team.id}">
        <div class="sidebar-team-header" onclick="this.parentElement.classList.toggle('collapsed')">
          <span class="sidebar-team-arrow"></span>
          <span class="sidebar-team-header-name">${esc(team.name)}</span>
          <span class="sidebar-team-header-count">(${team.agents.length})</span>
        </div>
        <div class="sidebar-team-agents">
          ${team.agents.length === 0
            ? `<div class="empty" style="padding:6px 16px 8px 32px;font-size:11px">${esc(t('sidebar.noAgentsInTeam'))}</div>`
            : team.agents.map(a => {
                const s = statsMap[a.address] || a;
                return _renderSidebarAgent({ ...s, ...a, agent_id: a.id, messages_unread: s.messages_unread || 0 }, activeAddr, true);
              }).join('')}
        </div>
      </div>`;
    }

    // Unassigned agents
    const assignedIds = new Set();
    for (const tm of teamDetails) for (const a of tm.agents) assignedIds.add(a.id);
    const unassigned = agentsList.filter(a => !assignedIds.has(a.id) && a.address !== HUMAN_OPERATOR_ADDRESS && a.role !== 'operator');
    if (unassigned.length > 0) {
      html += `<div class="sidebar-team-group" data-team-id="__unassigned">
        <div class="sidebar-team-header" onclick="this.parentElement.classList.toggle('collapsed')">
          <span class="sidebar-team-arrow"></span>
          <span class="sidebar-team-header-name">${esc(t('sidebar.unassigned'))}</span>
          <span class="sidebar-team-header-count">(${unassigned.length})</span>
        </div>
        <div class="sidebar-team-agents">
          ${unassigned.map(a => {
            const s = statsMap[a.address] || a;
            return _renderSidebarAgent({ ...s, ...a, agent_id: a.id, messages_unread: s.messages_unread || 0 }, activeAddr, true);
          }).join('')}
        </div>
      </div>`;
    }

    list.innerHTML = html || `<div class="empty" style="padding:20px 16px;font-size:12px">${esc(t('sidebar.emptyAgents'))}</div>`;
    return;
  }

  await fetchStats();
  // Build team name lookup for sidebar tags
  let teamNameMap = {};
  let agentTeamMap = {};
  try {
    if (typeof fetchTeams === 'function') {
      await fetchTeams();
      for (const tm of teamsData) teamNameMap[tm.id] = tm.name;
    }
    const agentsList = await fetchAgents();
    for (const a of agentsList) if (a.team_id) agentTeamMap[a.address] = a.team_id;
  } catch {}
  updateFilterVisibility();
  const activeAddr = currentView?.type === 'inbox' ? currentView.address : null;
  const filtered = filterTags.size > 0
    ? statsData.filter(a => a.address === HUMAN_OPERATOR_ADDRESS || (a.tags || []).some(tag => filterTags.has(tag)))
    : [...statsData];
  // Human Operator always first
  const filteredStats = filtered.sort((a, b) => {
    if (a.address === HUMAN_OPERATOR_ADDRESS) return -1;
    if (b.address === HUMAN_OPERATOR_ADDRESS) return 1;
    return 0;
  });
  list.innerHTML = filteredStats.length === 0 && filterTags.size > 0
    ? `<div class="empty" style="padding:20px 16px;font-size:12px">${esc(t('sidebar.emptyFilter'))}</div>`
    : filteredStats.map(a => {
    const tagsHtml = (a.tags || []).length > 0
      ? `<div class="sidebar-tags">${a.tags.map(tag => `<span class="sidebar-tag">${esc(tag)}</span>`).join('')}</div>`
      : '';
    const teamId = agentTeamMap[a.address];
    const teamTag = teamId && teamNameMap[teamId]
      ? ` <span class="sidebar-team-tag">${esc(teamNameMap[teamId])}</span>`
      : '';
    return `
    <div class="agent-item ${a.address === activeAddr ? 'active' : ''}"
         onclick='showInbox(${JSON.stringify(a.address)}, ${JSON.stringify(a.agent_id)})'>
      <div class="agent-info">
        <div class="agent-name"><span class="status-dot status-${a.status || 'offline'}" title="${esc(_statusTitle(a.status))}"></span>${esc(a.name)}${teamTag}</div>
        <div class="agent-role">${esc(a.role)} &middot; ${esc(a.address)}</div>
        ${tagsHtml}
      </div>
      <div style="display:flex;align-items:center;gap:6px">
        <span class="badge ${a.messages_unread === 0 ? 'zero' : ''}">${a.messages_unread}</span>
        <button class="agent-delete-btn" onclick="event.stopPropagation(); deleteAgent('${esc(a.agent_id)}', '${esc(a.name)}')" title="${esc(t('sidebar.deleteAgent'))}">&times;</button>
      </div>
    </div>`;
  }).join('');
}

function clearNav() {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.agent-item').forEach(b => b.classList.remove('active'));
  expandedMsg = null;
}
