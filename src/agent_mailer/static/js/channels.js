// --- Realtime chat channels: operator observability + kill-switch ---
//
// Talks to the cookie-authed /admin/channels endpoints. Auto-refreshes via the
// global poller (see events.js: currentView.type 'channels' | 'channel').

function channelStatusBadge(status) {
  const map = {
    open: ['#1f9d55', 'OPEN'],
    pending_human: ['#b7791f', 'PAUSED'],
    closed: ['#718096', 'CLOSED'],
  };
  const [color, label] = map[status] || ['#718096', String(status || '').toUpperCase()];
  return `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;color:#fff;background:${color}">${esc(label)}</span>`;
}

function shortToken(tok) {
  const s = String(tok || '');
  return s.length > 12 ? `${s.slice(0, 8)}…${s.slice(-2)}` : s;
}

async function showChannels() {
  currentView = { type: 'channels' };
  document.getElementById('main').innerHTML =
    `<div class="card"><h2>Chat Channels</h2><p>Loading…</p></div>`;
  try {
    await renderChannelsList();
  } catch (e) {
    document.getElementById('main').innerHTML =
      `<div class="card"><h2>Chat Channels</h2><p class="empty">${esc(t('common.errorPrefix'))}${esc(e.message || e)}</p></div>`;
  }
}

async function renderChannelsList() {
  if (currentView?.type !== 'channels') return;
  const channels = await api('/admin/channels');
  const main = document.getElementById('main');
  if (!channels.length) {
    main.innerHTML = `<div class="card"><h2>Chat Channels</h2><p class="empty">No channels yet.</p></div>`;
    return;
  }
  const rows = channels.map((c) => {
    const members = (c.members || []).map((m) => esc(m.agent_address)).join('<br>') || '—';
    const actions = channelActionButtons(c);
    return `
      <tr>
        <td><span class="thread-link" onclick="showChannel('${esc(c.join_token)}')">${esc(shortToken(c.join_token))}</span></td>
        <td>${channelStatusBadge(c.status)}${c.close_reason ? `<div style="font-size:11px;color:var(--muted);margin-top:2px">${esc(c.close_reason)}</div>` : ''}</td>
        <td>${esc(c.creator_agent)}</td>
        <td style="font-size:12px">${members}</td>
        <td style="text-align:center">${c.turn_count}/${c.max_turns}</td>
        <td style="font-size:12px;color:var(--muted)">${fmtTime(c.created_at)}</td>
        <td>${actions}</td>
      </tr>`;
  }).join('');
  main.innerHTML = `
    <div class="card">
      <h2>Chat Channels</h2>
      <table class="data-table" style="width:100%">
        <thead><tr>
          <th>Token</th><th>Status</th><th>Creator</th><th>Members</th><th>Turns</th><th>Created</th><th>Actions</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function channelActionButtons(c) {
  const btns = [];
  if (c.status === 'pending_human') {
    btns.push(`<button type="button" class="btn btn-primary" style="font-size:12px;padding:4px 10px" onclick="continueChannel('${esc(c.join_token)}', event)">Continue</button>`);
  }
  if (c.status !== 'closed') {
    btns.push(`<button type="button" class="btn btn-secondary" style="font-size:12px;padding:4px 10px" onclick="closeChannel('${esc(c.join_token)}', event)">Close</button>`);
  }
  return btns.join(' ') || '—';
}

async function showChannel(token) {
  currentView = { type: 'channel', token };
  document.getElementById('main').innerHTML =
    `<div class="card"><h2>Channel</h2><p>Loading…</p></div>`;
  try {
    await renderChannelView();
  } catch (e) {
    document.getElementById('main').innerHTML =
      `<div class="card"><h2>Channel</h2><p class="empty">${esc(t('common.errorPrefix'))}${esc(e.message || e)}</p></div>`;
  }
}

async function renderChannelView() {
  if (currentView?.type !== 'channel') return;
  const token = currentView.token;
  const data = await api(`/admin/channels/${encodeURIComponent(token)}`);
  const c = data.channel;
  const msgs = data.messages || [];
  const main = document.getElementById('main');

  const seed = c.initial_prompt
    ? `<div class="thread-msg"><div class="thread-meta"><strong>${esc(c.creator_agent)}</strong> <span class="msg-action-tag send" style="margin-left:6px">prompt</span></div><div class="thread-body">${esc(c.initial_prompt)}</div></div>`
    : '';
  const bubbles = msgs.map((m) => `
    <div class="thread-msg">
      <div class="thread-meta">
        <strong>${esc(m.from_agent)}</strong>
        <span style="margin-left:8px;color:var(--muted)">#${m.seq} · ${fmtTime(m.created_at)}</span>
      </div>
      <div class="thread-body markdown-body" data-md-html="${mdDataAttr(m.body_html || '')}"></div>
    </div>`).join('');

  const members = (c.members || []).map((m) => `${esc(m.agent_address)} <span style="color:var(--muted)">(${esc(m.role)})</span>`).join(' · ');
  const ctrls = channelActionButtons(c);

  main.innerHTML = `
    <button type="button" class="back-btn" onclick="showChannels()">&larr; Channels</button>
    <div class="card">
      <h2>Channel ${channelStatusBadge(c.status)}</h2>
      <div style="font-size:13px;color:var(--muted);margin-bottom:6px">
        <div>Members: ${members || '—'}</div>
        <div>Turns: ${c.turn_count}/${c.max_turns} · TTL: ${fmtTime(c.ttl_expires_at)}${c.close_reason ? ` · reason: ${esc(c.close_reason)}` : ''}</div>
      </div>
      <div class="thread-actions" style="margin-bottom:10px">${ctrls}</div>
      ${seed}
      ${bubbles || '<p class="empty">No messages yet.</p>'}
    </div>`;
  hydrateMarkdownBodies(main);
}

async function closeChannel(token, event) {
  if (event) event.stopPropagation();
  try {
    await api(`/admin/channels/${encodeURIComponent(token)}/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'human' }),
    });
  } catch (e) {
    alert(`${t('common.errorPrefix')}${e.message || e}`);
    return;
  }
  if (currentView?.type === 'channel') await renderChannelView();
  else await renderChannelsList();
}

async function continueChannel(token, event) {
  if (event) event.stopPropagation();
  try {
    await api(`/admin/channels/${encodeURIComponent(token)}/continue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),  // server defaults: +10 turns / +30 min
    });
  } catch (e) {
    alert(`${t('common.errorPrefix')}${e.message || e}`);
    return;
  }
  if (currentView?.type === 'channel') await renderChannelView();
  else await renderChannelsList();
}
