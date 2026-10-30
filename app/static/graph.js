(() => {
  const mount = document.getElementById('graph-canvas');
  if (!mount || typeof ForceGraph === 'undefined') return;

  const panel = document.getElementById('node-panel');
  const panelBody = document.getElementById('node-panel-body');
  const panelClose = document.getElementById('node-panel-close');
  const legendList = document.getElementById('graph-legend-list');
  const emptyNote = document.getElementById('graph-empty');
  const searchInput = document.getElementById('graph-search-input');
  const searchCount = document.getElementById('graph-search-count');
  const aiToggle = document.getElementById('graph-ai-toggle');
  const resetBtn = document.getElementById('graph-reset');
  const showAllBtn = document.getElementById('graph-show-all');
  const loadingEl = document.getElementById('graph-loading');
  const exportBar = document.getElementById('graph-export-bar');
  const exportCount = document.getElementById('graph-export-count');
  const exportDepth = document.getElementById('graph-export-depth');
  const exportGo = document.getElementById('graph-export-go');
  const exportClear = document.getElementById('graph-export-clear');
  const dateBar = document.querySelector('.graph-timebar');
  const dateFromInput = document.getElementById('graph-date-from');
  const dateToInput = document.getElementById('graph-date-to');
  const dateContextInput = document.getElementById('graph-date-context');
  const dateStatus = document.getElementById('graph-date-status');
  const datePresetButtons = [...document.querySelectorAll('[data-date-preset]')];

  const PROGRESSIVE_CAP = 400; // nodes shown before progressive disclosure kicks in

  const COLORS = {
    memory: '#00e6ff',
    action: '#fced1a',
    person: '#fced1a',
    organization: '#b26bff',
    project: '#39ff7a',
    concept: '#ff8a3d',
    event: '#ff3366',
    technology: '#00e0c8',
    place: '#ffae2e',
    topic: '#9aa0c8',
    other: '#8a8ca0',
  };
  const INK = '#e9ecff';
  const ACCENT = '#fced1a';
  const DONE = '#39ff7a';
  const colorFor = (node) => COLORS[node.category] || COLORS.other;
  const isConcluded = (node) => node?.metadata?.task_status === 'done';

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const CAM = reduceMotion ? 0 : 600; // camera transition duration
  const radiusFor = (node) =>
    Math.min(Math.max(4 + Math.sqrt(node.__degree || 0) * 1.5, 4), 13);

  // UI strings (chrome only — never node content)
  const LANG = document.documentElement.lang || 'en';
  const STR = {
    'pt-BR': {
      'Connections': 'Conexões',
      'Open full memory →': 'Abrir memória completa →',
      'Source': 'Fonte',
      'Source-grounded': 'Baseado na fonte',
      'AI-inferred': 'Inferido por IA',
      'Loading…': 'Carregando…',
      'Could not load this node.': 'Não foi possível carregar este nó.',
      'Could not load the graph.': 'Não foi possível carregar o grafo.',
      'Isolate': 'Isolar',
      'Show all': 'Mostrar tudo',
      'no matches': 'nenhuma correspondência',
      'match': 'correspondência',
      'matches': 'correspondências',
      'Add to export': 'Adicionar à exportação',
      'In export set': 'No conjunto de exportação',
      'selected': 'selecionado(s)',
      'Concluded': 'Concluída',
      'All dates': 'Todas as datas',
      'nodes': 'nós',
      'Dated': 'Datados',
      'Context': 'Contexto',
      'Start date must be before end date.': 'A data inicial deve ser anterior à data final.',
    },
  };
  const tr = (s) => (STR[LANG] && STR[LANG][s]) || s;

  const escapeHtml = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (ch) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));

  const idOf = (ref) => (typeof ref === 'object' && ref ? ref.id : ref);

  // --- exploration state --------------------------------------------------
  let selectedId = null;
  let connected = new Set();
  let hoverId = null;
  let hoverSet = new Set();
  let searchTerm = '';
  const hiddenCats = new Set();
  let showAi = true;
  let isolateId = null;
  let isolateSet = new Set();
  const exportSet = new Set(); // nodes chosen for a subgraph export
  let progThreshold = 0; // min degree to show when progressively disclosed
  let showAllNodes = false;
  let dateFrom = '';
  let dateTo = '';
  let dateInvalid = false;
  let dateContextIds = new Set();

  const allNodesById = new Map();

  function nodeDateKey(node) {
    const value = node?.occurred_at;
    const match = typeof value === 'string' ? value.match(/^(\d{4}-\d{2}-\d{2})/) : null;
    return match ? match[1] : null;
  }

  const dateFilterActive = () => Boolean(dateFrom || dateTo);

  function nodeInDateRange(node) {
    const key = nodeDateKey(node);
    if (!key) return false;
    return (!dateFrom || key >= dateFrom) && (!dateTo || key <= dateTo);
  }

  function recomputeDateContext() {
    // Seed from the dated nodes inside the window, then walk outward through
    // undated nodes only, collecting the full reachable neighborhood. Other
    // dated nodes (outside the window, or inside it) act as walls, so one
    // period's context never leaks across a memory into another period.
    dateContextIds = new Set();
    if (!dateFilterActive() || dateInvalid || !dateContextInput?.checked) return;
    const adjacency = new Map();
    for (const link of Graph.graphData().links) {
      if (!showAi && link.provenance === 'ai_inferred') continue;
      const sourceId = idOf(link.source);
      const targetId = idOf(link.target);
      if (!adjacency.has(sourceId)) adjacency.set(sourceId, []);
      if (!adjacency.has(targetId)) adjacency.set(targetId, []);
      adjacency.get(sourceId).push(targetId);
      adjacency.get(targetId).push(sourceId);
    }
    const queue = [...allNodesById.values()].filter(nodeInDateRange).map((node) => node.id);
    const seen = new Set(queue);
    while (queue.length) {
      const id = queue.shift();
      for (const next of adjacency.get(id) || []) {
        if (seen.has(next)) continue;
        seen.add(next);
        const node = allNodesById.get(next);
        if (!node || nodeDateKey(node)) continue; // stop at dated nodes
        dateContextIds.add(next);
        queue.push(next);
      }
    }
  }

  function dateAllows(node) {
    if (!dateFilterActive() || dateInvalid) return true;
    if (nodeInDateRange(node)) return true;
    return !nodeDateKey(node) && dateContextIds.has(node.id);
  }

  const matches = (node) =>
    !searchTerm || (node.label || '').toLowerCase().includes(searchTerm);

  function nodeVisible(node) {
    if (!dateAllows(node)) return false;
    if (hiddenCats.has(node.category)) return false;
    if (isolateId && node.id !== isolateId && !isolateSet.has(node.id)) return false;
    if (progThreshold && !showAllNodes && !isolateId && (node.__degree || 0) < progThreshold) {
      return false;
    }
    return true;
  }

  function linkVisible(link) {
    if (!showAi && link.provenance === 'ai_inferred') return false;
    const s = allNodesById.get(idOf(link.source));
    const t = allNodesById.get(idOf(link.target));
    return !!(s && t && nodeVisible(s) && nodeVisible(t));
  }

  function refresh() {
    // Re-assigning the accessors makes force-graph re-evaluate and redraw.
    Graph.nodeVisibility(nodeVisible).linkVisibility(linkVisible);
  }

  const Graph = ForceGraph()(mount)
    .nodeId('id')
    .nodeLabel((node) => `${escapeHtml(node.label)} · ${node.category}${isConcluded(node) ? ` · ${tr('Concluded')}` : ''}`)
    .nodeRelSize(5)
    .nodeVisibility(nodeVisible)
    .linkVisibility(linkVisible)
    .linkLabel((link) => escapeHtml(link.label || ''))
    .linkDirectionalArrowLength((link) => (link.directed === false ? 0 : 4))
    .linkDirectionalArrowRelPos(1)
    .linkCurvature(0.08)
    .cooldownTicks(120)
    .nodeCanvasObject((node, ctx, scale) => {
      const dimSel = selectedId && node.id !== selectedId && !connected.has(node.id);
      const dimSearch = searchTerm && !matches(node);
      const faded = dimSel || dimSearch;
      const hit = searchTerm && matches(node);
      const emphasised = node.id === selectedId || node.id === hoverId;
      const concluded = isConcluded(node);
      const color = colorFor(node);
      const radius = radiusFor(node) + (emphasised ? 2 : 0);
      ctx.globalAlpha = faded ? 0.16 : 1;

      // Neon glow
      ctx.shadowColor = color;
      ctx.shadowBlur = faded ? 0 : (emphasised ? 18 : 10);
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.shadowBlur = 0;

      if (emphasised || hit) {
        ctx.lineWidth = (emphasised ? 2 : 2.5) / scale;
        ctx.strokeStyle = node.id === selectedId ? INK : (hit ? ACCENT : color);
        ctx.stroke();
      }

      if (concluded) {
        ctx.globalAlpha = faded ? 0.3 : 1;
        ctx.lineWidth = 2.3 / scale;
        ctx.strokeStyle = DONE;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.fillStyle = '#06130b';
        ctx.font = `bold ${Math.max(10 / scale, 3)}px Inter, system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('✓', node.x, node.y + .5 / scale);
      }

      if (scale > 1.4 || emphasised || connected.has(node.id) || hoverSet.has(node.id) || hit) {
        const fontSize = Math.max(11 / scale, 2.5);
        ctx.font = `${fontSize}px Inter, system-ui, -apple-system, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = INK;
        ctx.fillText(node.label, node.x, node.y + radius + 1.5);
      }

      if (exportSet.has(node.id)) {
        ctx.globalAlpha = 1;
        ctx.setLineDash([3 / scale, 3 / scale]);
        ctx.lineWidth = 2.5 / scale;
        ctx.strokeStyle = ACCENT;
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 4, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      ctx.globalAlpha = 1;
    })
    .nodePointerAreaPaint((node, color, ctx) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radiusFor(node) + 2, 0, 2 * Math.PI);
      ctx.fill();
    })
    .linkColor((link) => {
      const s = idOf(link.source);
      const t = idOf(link.target);
      const onSel = selectedId && (s === selectedId || t === selectedId);
      const onHover = hoverId && (s === hoverId || t === hoverId);
      if (onSel || onHover) return 'rgba(0,230,255,0.9)';
      if (selectedId || searchTerm) return 'rgba(233,236,255,0.05)';
      return link.provenance === 'ai_inferred' ? 'rgba(255,46,151,0.42)' : 'rgba(233,236,255,0.2)';
    })
    .linkWidth((link) => {
      const s = idOf(link.source);
      const t = idOf(link.target);
      return (hoverId && (s === hoverId || t === hoverId)) ? 2 : 1;
    })
    .linkLineDash((link) => (link.provenance === 'ai_inferred' ? [3, 3] : null))
    .onNodeHover((node) => {
      hoverId = node ? node.id : null;
      hoverSet = new Set();
      if (node) {
        for (const link of Graph.graphData().links) {
          const s = idOf(link.source);
          const t = idOf(link.target);
          if (s === node.id) hoverSet.add(t);
          else if (t === node.id) hoverSet.add(s);
        }
      }
      mount.style.cursor = node ? 'pointer' : 'grab';
    })
    .onNodeClick((node, event) => {
      if (event && (event.shiftKey || event.ctrlKey || event.metaKey)) {
        toggleExport(node.id);
        return;
      }
      selectNode(node.id);
      Graph.centerAt(node.x, node.y, CAM);
      Graph.zoom(Math.max(Graph.zoom(), 2.2), CAM);
    })
    .onBackgroundClick(() => clearSelection());

  function sizeToContainer() {
    Graph.width(mount.clientWidth).height(mount.clientHeight);
  }
  window.addEventListener('resize', sizeToContainer);

  // --- legend as category filters ----------------------------------------
  function buildLegend(categories) {
    legendList.replaceChildren(...categories.map((category) => {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'legend-item';
      btn.setAttribute('aria-pressed', 'true');
      const swatch = document.createElement('span');
      swatch.className = 'legend-swatch';
      swatch.style.background = COLORS[category] || COLORS.other;
      const label = document.createElement('span');
      label.textContent = category;
      btn.append(swatch, label);
      btn.addEventListener('click', () => {
        if (hiddenCats.has(category)) hiddenCats.delete(category);
        else hiddenCats.add(category);
        const on = !hiddenCats.has(category);
        btn.setAttribute('aria-pressed', String(on));
        btn.classList.toggle('is-off', !on);
        refresh();
      });
      li.append(btn);
      return li;
    }));
  }

  function selectNode(nodeId) {
    selectedId = nodeId;
    connected = new Set();
    for (const link of Graph.graphData().links) {
      const s = idOf(link.source);
      const t = idOf(link.target);
      if (s === nodeId) connected.add(t);
      else if (t === nodeId) connected.add(s);
    }
    openPanel(nodeId);
  }

  function clearSelection() {
    selectedId = null;
    connected = new Set();
    panel.hidden = true;
  }

  function neighborMarkup(detail) {
    if (!detail.neighbors || !detail.neighbors.length) return '';
    const visibleNeighbors = detail.neighbors.filter((n) => {
      const node = n.node && allNodesById.get(n.node.id);
      return node && nodeVisible(node);
    });
    if (!visibleNeighbors.length) return '';
    const items = visibleNeighbors
      .map((n) => {
        const arrow = n.direction === 'out' ? '→' : '←';
        return `<li><button type="button" class="node-link" data-id="${escapeHtml(n.node.id)}">
          <span class="rel">${arrow} ${escapeHtml(n.edge.label)}</span>
          <span class="rel-node">${escapeHtml(n.node.label)}</span>
          <span class="rel-cat">${escapeHtml(n.node.category)}</span>
        </button></li>`;
      })
      .join('');
    return `<h3 class="panel-subhead">${tr('Connections')} <span>${visibleNeighbors.length}</span></h3>
            <ul class="node-links">${items}</ul>`;
  }

  function sourceMarkup(detail) {
    if (!detail.source_label && !detail.source_type) return '';
    const excerpt = detail.source_excerpt
      ? `<blockquote>${escapeHtml(detail.source_excerpt)}</blockquote>` : '';
    return `<div class="panel-source"><span class="panel-label">${tr('Source')}</span>
      <p>${escapeHtml(detail.source_type || '')}${detail.source_label ? ' · ' + escapeHtml(detail.source_label) : ''}</p>
      ${excerpt}</div>`;
  }

  function metaMarkup(detail) {
    if (!detail.metadata) return '';
    const rows = Object.entries(detail.metadata)
      .map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`)
      .join('');
    return `<dl class="panel-meta">${rows}</dl>`;
  }

  function setIsolate(nodeId) {
    isolateId = nodeId;
    isolateSet = new Set();
    if (nodeId) {
      for (const link of Graph.graphData().links) {
        const s = idOf(link.source);
        const t = idOf(link.target);
        if (s === nodeId) isolateSet.add(t);
        else if (t === nodeId) isolateSet.add(s);
      }
    }
    refresh();
    if (nodeId) {
      Graph.zoomToFit(CAM, 70, (n) => n.id === nodeId || isolateSet.has(n.id));
    } else {
      Graph.zoomToFit(CAM, 60);
    }
  }

  function exportHref() {
    const ids = [...exportSet].map(encodeURIComponent).join(',');
    const depth = Math.max(1, Math.min(parseInt(exportDepth?.value, 10) || 3, 6));
    return `/export/graph.json?nodes=${ids}&depth=${depth}`;
  }

  function updateExportBar() {
    if (!exportBar) return;
    const n = exportSet.size;
    exportBar.hidden = n === 0;
    if (exportCount) exportCount.textContent = `${n} ${tr('selected')}`;
    if (exportGo) exportGo.href = exportHref();
  }

  function toggleExport(nodeId) {
    if (exportSet.has(nodeId)) exportSet.delete(nodeId);
    else exportSet.add(nodeId);
    updateExportBar();
    refresh();
  }

  async function openPanel(nodeId) {
    panel.hidden = false;
    panelBody.innerHTML = `<p class="panel-loading">${tr('Loading…')}</p>`;
    let detail;
    try {
      const res = await fetch(`/nodes/${encodeURIComponent(nodeId)}`);
      if (!res.ok) throw new Error('not found');
      detail = await res.json();
    } catch (err) {
      panelBody.innerHTML = `<p class="panel-loading">${tr('Could not load this node.')}</p>`;
      return;
    }

    const isolated = isolateId === nodeId;
    const record = detail.record_id
      ? `<a class="panel-record" href="/memories/${encodeURIComponent(detail.record_id)}">${tr('Open full memory →')}</a>`
      : '';
    const provenance = detail.provenance === 'ai_inferred'
      ? `<span class="badge badge-ai">${tr('AI-inferred')}</span>`
      : `<span class="badge badge-source">${tr('Source-grounded')}</span>`;
    const status = isConcluded(detail)
      ? `<span class="badge badge-done">${tr('Concluded')}</span>` : '';

    panelBody.innerHTML = `
      <p class="panel-eyebrow"><span class="cat-dot" style="background:${colorFor(detail)}"></span>${escapeHtml(detail.category)} ${provenance} ${status}</p>
      <h2 class="panel-title">${escapeHtml(detail.label)}</h2>
      ${detail.description ? `<p class="panel-desc">${escapeHtml(detail.description)}</p>` : ''}
      ${detail.occurred_at ? `<p class="panel-when">${escapeHtml(detail.occurred_at)}</p>` : ''}
      <div class="panel-tools">
        <button type="button" class="panel-isolate" data-isolated="${isolated}">${isolated ? tr('Show all') : tr('Isolate')}</button>
        <button type="button" class="panel-export" data-inset="${exportSet.has(nodeId)}">${exportSet.has(nodeId) ? tr('In export set') : tr('Add to export')}</button>
      </div>
      ${sourceMarkup(detail)}
      ${metaMarkup(detail)}
      ${record}
      ${neighborMarkup(detail)}
    `;

    panelBody.querySelector('.panel-isolate')?.addEventListener('click', () => {
      setIsolate(isolateId === nodeId ? null : nodeId);
      openPanel(nodeId); // refresh button label
    });

    panelBody.querySelector('.panel-export')?.addEventListener('click', () => {
      toggleExport(nodeId);
      openPanel(nodeId); // refresh button label
    });

    panelBody.querySelectorAll('.node-link').forEach((btn) => {
      btn.addEventListener('click', () => {
        const target = Graph.graphData().nodes.find((n) => n.id === btn.dataset.id);
        selectNode(btn.dataset.id);
        if (target && target.x != null) {
          Graph.centerAt(target.x, target.y, CAM);
          Graph.zoom(Math.max(Graph.zoom(), 2.2), CAM);
        }
      });
    });
    panel.focus();
  }

  // --- toolbar wiring -----------------------------------------------------
  function updateSearchCount() {
    if (!searchCount) return;
    if (!searchTerm) { searchCount.textContent = ''; return; }
    const n = Graph.graphData().nodes.filter((node) => nodeVisible(node) && matches(node)).length;
    if (n === 0) searchCount.textContent = tr('no matches');
    else searchCount.textContent = `${n} ${n === 1 ? tr('match') : tr('matches')}`;
  }

  function setActiveDatePreset(value) {
    datePresetButtons.forEach((button) => {
      const active = button.dataset.datePreset === value;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }

  function localDateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function updateDateStatus() {
    if (!dateStatus) return;
    dateBar?.classList.toggle('is-active', dateFilterActive() && !dateInvalid);
    dateFromInput?.setAttribute('aria-invalid', String(dateInvalid));
    dateToInput?.setAttribute('aria-invalid', String(dateInvalid));
    if (dateInvalid) {
      dateStatus.textContent = tr('Start date must be before end date.');
      dateStatus.classList.add('is-error');
      return;
    }
    dateStatus.classList.remove('is-error');
    if (!dateFilterActive()) {
      dateStatus.textContent = `${tr('All dates')} · ${allNodesById.size} ${tr('nodes')}`;
      return;
    }
    const dated = [...allNodesById.values()].filter(nodeInDateRange).length;
    const context = dateContextInput?.checked ? dateContextIds.size : 0;
    dateStatus.textContent = `${tr('Dated')}: ${dated} · ${tr('Context')}: ${context}`;
  }

  function applyDateFilter({ fit = true } = {}) {
    dateFrom = dateFromInput?.value || '';
    dateTo = dateToInput?.value || '';
    dateInvalid = Boolean(dateFrom && dateTo && dateFrom > dateTo);
    recomputeDateContext();
    if (selectedId && !dateAllows(allNodesById.get(selectedId))) clearSelection();
    if (isolateId && !dateAllows(allNodesById.get(isolateId))) {
      isolateId = null;
      isolateSet = new Set();
    }
    updateDateStatus();
    refresh();
    updateSearchCount();
    if (fit && allNodesById.size && !dateInvalid) {
      requestAnimationFrame(() => Graph.zoomToFit(CAM, 60, nodeVisible));
    }
  }

  function chooseDatePreset(value) {
    if (!dateFromInput || !dateToInput) return;
    if (value === 'all') {
      dateFromInput.value = '';
      dateToInput.value = '';
    } else {
      const end = new Date();
      end.setHours(12, 0, 0, 0);
      const start = new Date(end);
      const days = value === 'today' ? 1 : Number.parseInt(value, 10);
      start.setDate(start.getDate() - Math.max(days - 1, 0));
      dateFromInput.value = localDateKey(start);
      dateToInput.value = localDateKey(end);
    }
    setActiveDatePreset(value);
    applyDateFilter();
  }

  searchInput?.addEventListener('input', () => {
    searchTerm = searchInput.value.trim().toLowerCase();
    refresh();
    updateSearchCount();
  });
  searchInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && searchTerm) {
      e.preventDefault();
      const hits = Graph.graphData().nodes.filter((n) => nodeVisible(n) && matches(n));
      if (hits.length) Graph.zoomToFit(CAM, 80, (n) => nodeVisible(n) && matches(n));
    }
  });

  aiToggle?.addEventListener('change', () => {
    showAi = aiToggle.checked;
    applyDateFilter({ fit: false });
  });

  datePresetButtons.forEach((button) => {
    button.addEventListener('click', () => chooseDatePreset(button.dataset.datePreset));
  });
  [dateFromInput, dateToInput].forEach((input) => {
    input?.addEventListener('change', () => {
      setActiveDatePreset(null);
      applyDateFilter();
    });
  });
  dateContextInput?.addEventListener('change', () => applyDateFilter());

  exportDepth?.addEventListener('input', updateExportBar);
  exportGo?.addEventListener('click', () => { if (exportGo) exportGo.href = exportHref(); });
  exportClear?.addEventListener('click', () => {
    exportSet.clear();
    updateExportBar();
    refresh();
  });

  resetBtn?.addEventListener('click', () => {
    searchTerm = '';
    if (searchInput) searchInput.value = '';
    hiddenCats.clear();
    showAi = true;
    if (aiToggle) aiToggle.checked = true;
    isolateId = null;
    isolateSet = new Set();
    showAllNodes = false;
    if (dateFromInput) dateFromInput.value = '';
    if (dateToInput) dateToInput.value = '';
    if (dateContextInput) dateContextInput.checked = true;
    dateFrom = '';
    dateTo = '';
    dateInvalid = false;
    dateContextIds = new Set();
    setActiveDatePreset('all');
    exportSet.clear();
    updateExportBar();
    clearSelection();
    legendList.querySelectorAll('.legend-item').forEach((b) => {
      b.setAttribute('aria-pressed', 'true');
      b.classList.remove('is-off');
    });
    updateProgButton();
    updateDateStatus();
    refresh();
    updateSearchCount();
    Graph.zoomToFit(CAM, 60);
  });

  function updateProgButton() {
    if (!showAllBtn) return;
    showAllBtn.hidden = !(progThreshold && !showAllNodes);
  }
  showAllBtn?.addEventListener('click', () => {
    showAllNodes = true;
    updateProgButton();
    refresh();
    Graph.zoomToFit(CAM, 60);
  });

  panelClose.addEventListener('click', clearSelection);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !panel.hidden) clearSelection();
  });

  fetch('/graph.json')
    .then((res) => res.json())
    .then((data) => {
      sizeToContainer();
      if (loadingEl) loadingEl.hidden = true;
      if (!data.nodes.length) {
        emptyNote.hidden = false;
        return;
      }
      // Degrees for progressive disclosure + hub emphasis.
      for (const node of data.nodes) { node.__degree = 0; allNodesById.set(node.id, node); }
      for (const edge of data.edges) {
        const s = allNodesById.get(idOf(edge.source));
        const t = allNodesById.get(idOf(edge.target));
        if (s) s.__degree += 1;
        if (t) t.__degree += 1;
      }
      recomputeDateContext();
      updateDateStatus();
      // Progressive disclosure: for large graphs, start with the highest-degree
      // nodes (capped), and expose "show all" to reveal the rest.
      if (data.nodes.length > PROGRESSIVE_CAP) {
        const degrees = data.nodes.map((n) => n.__degree).sort((a, b) => b - a);
        progThreshold = degrees[PROGRESSIVE_CAP - 1] || 1;
      }
      updateProgButton();

      const categories = [...new Set(data.nodes.map((n) => n.category))].sort();
      buildLegend(categories);

      let didFit = false;
      Graph.onEngineStop(() => {
        if (!didFit) { Graph.zoomToFit(500, 60); didFit = true; }
      });
      if (reduceMotion) {
        Graph.cooldownTicks(0);
        Graph.d3AlphaDecay(0.2);
      }
      Graph.graphData({ nodes: data.nodes, links: data.edges });
      setTimeout(() => { if (!didFit) { Graph.zoomToFit(500, 60); didFit = true; } }, 1500);
    })
    .catch(() => {
      if (loadingEl) loadingEl.hidden = true;
      emptyNote.hidden = false;
      emptyNote.textContent = tr('Could not load the graph.');
    });
})();
