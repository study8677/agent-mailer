// --- Helpers ---
function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function mdDataAttr(html) {
  if (html == null || html === '') return '';
  return encodeURIComponent(html);
}

function hydrateMarkdownBodies(root) {
  if (!root) return;
  root.querySelectorAll('[data-md-html]').forEach(el => {
    const enc = el.getAttribute('data-md-html');
    el.removeAttribute('data-md-html');
    if (enc == null || enc === '') return;
    try {
      el.innerHTML = decodeURIComponent(enc);
    } catch (err) {
      el.textContent = '(Failed to render message body)';
      return;
    }
    el.querySelectorAll('a[href]').forEach(a => {
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
      a.addEventListener('click', e => e.stopPropagation());
    });
  });
}

function fmtTime(iso) {
  const d = new Date(iso);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
         d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// --- Confirm modal ---
function showConfirm(title, body, confirmLabel) {
  return new Promise(resolve => {
    const overlay = document.getElementById('confirmModal');
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmBody').textContent = body;
    const okBtn = document.getElementById('confirmOk');
    okBtn.textContent = confirmLabel || '确认';
    overlay.classList.add('visible');

    function cleanup(result) {
      overlay.classList.remove('visible');
      okBtn.removeEventListener('click', onOk);
      document.getElementById('confirmCancel').removeEventListener('click', onCancel);
      overlay.removeEventListener('click', onBackdrop);
      resolve(result);
    }
    function onOk() { cleanup(true); }
    function onCancel() { cleanup(false); }
    function onBackdrop(e) { if (e.target === overlay) cleanup(false); }

    okBtn.addEventListener('click', onOk);
    document.getElementById('confirmCancel').addEventListener('click', onCancel);
    overlay.addEventListener('click', onBackdrop);
  });
}
