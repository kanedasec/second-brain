(() => {
  const mount = document.getElementById('graph-canvas');
  if (!mount || typeof ForceGraph === 'undefined') return;

  const panel = document.getElementById('node-panel');
  const panelBody = document.getElementById('node-panel-body');
  const panelClose = document.getElementById('node-panel-close');
  const legendList = document.getElementById('graph-legend-list');
  const emptyNote = document.getElementById('graph-empty');

  // Category palette — warm paper, one electric-blue accent for memories.
  const COLORS = {
    memory: '#00e6ff',
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
  const colorFor = (node) => COLORS[node.category] || COLORS.other;

  const escapeHtml = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (ch) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));

  let selectedId = null;
  let connected = new Set(); // node ids adjacent to the selection

  const Graph = ForceGraph()(mount)
    .nodeId('id')
    .nodeLabel((node) => `${escapeHtml(node.label)} · ${node.category}`)
    .nodeRelSize(5)
    .linkLabel((link) => escapeHtml(link.label || ''))
    .linkDirectionalArrowLength((link) => (link.directed === false ? 0 : 4))
    .linkDirectionalArrowRelPos(1)
    .linkCurvature(0.08)
    .cooldownTicks(120)
    .nodeCanvasObject((node, ctx, scale) => {
      const faded = selectedId && node.id !== selectedId && !connected.has(node.id);
      const radius = node.id === selectedId ? 7 : 5;
      ctx.globalAlpha = faded ? 0.25 : 1;

      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = colorFor(node);
      ctx.fill();
      if (node.id === selectedId) {
        ctx.lineWidth = 2 / scale;
        ctx.strokeStyle = INK;
        ctx.stroke();
      }

      if (scale > 1.4 || node.id === selectedId || connected.has(node.id)) {
        const fontSize = Math.max(11 / scale, 2.5);
        ctx.font = `${fontSize}px Georgia, 'Times New Roman', serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillStyle = INK;
        ctx.fillText(node.label, node.x, node.y + radius + 1.5);
      }
      ctx.globalAlpha = 1;
    })
    .nodePointerAreaPaint((node, color, ctx) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI);
      ctx.fill();
    })
    .linkColor((link) => {
      const active = selectedId
        && (idOf(link.source) === selectedId || idOf(link.target) === selectedId);
      if (active) return 'rgba(0,230,255,0.85)';
      if (selectedId) return 'rgba(233,236,255,0.06)';
      return link.provenance === 'ai_inferred' ? 'rgba(255,46,151,0.42)' : 'rgba(233,236,255,0.2)';
    })
    .linkLineDash((link) => (link.provenance === 'ai_inferred' ? [3, 3] : null))
    .onNodeClick((node) => {
      selectNode(node.id);
      Graph.centerAt(node.x, node.y, 600);
      Graph.zoom(Math.max(Graph.zoom(), 2.2), 600);
    })
    .onBackgroundClick(() => clearSelection());

  const idOf = (ref) => (typeof ref === 'object' && ref ? ref.id : ref);

  function sizeToContainer() {
    Graph.width(mount.clientWidth).height(mount.clientHeight);
  }
  window.addEventListener('resize', sizeToContainer);

  function buildLegend(categories) {
    legendList.replaceChildren(...categories.map((category) => {
      const li = document.createElement('li');
      const swatch = document.createElement('span');
      swatch.className = 'legend-swatch';
      swatch.style.background = COLORS[category] || COLORS.other;
      const label = document.createElement('span');
      label.textContent = category;
      li.append(swatch, label);
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
    const items = detail.neighbors
      .filter((n) => n.node)
      .map((n) => {
        const arrow = n.direction === 'out' ? '→' : '←';
        return `<li><button type="button" class="node-link" data-id="${escapeHtml(n.node.id)}">
          <span class="rel">${arrow} ${escapeHtml(n.edge.label)}</span>
          <span class="rel-node">${escapeHtml(n.node.label)}</span>
          <span class="rel-cat">${escapeHtml(n.node.category)}</span>
        </button></li>`;
      })
      .join('');
    return `<h3 class="panel-subhead">Connections <span>${detail.neighbors.length}</span></h3>
            <ul class="node-links">${items}</ul>`;
  }

  function sourceMarkup(detail) {
    if (!detail.source_label && !detail.source_type) return '';
    const excerpt = detail.source_excerpt
      ? `<blockquote>${escapeHtml(detail.source_excerpt)}</blockquote>` : '';
    return `<div class="panel-source"><span class="panel-label">Source</span>
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

  async function openPanel(nodeId) {
    panel.hidden = false;
    panelBody.innerHTML = '<p class="panel-loading">Loading…</p>';
    let detail;
    try {
      const res = await fetch(`/nodes/${encodeURIComponent(nodeId)}`);
      if (!res.ok) throw new Error('not found');
      detail = await res.json();
    } catch (err) {
      panelBody.innerHTML = '<p class="panel-loading">Could not load this node.</p>';
      return;
    }

    const record = detail.record_id
      ? `<a class="panel-record" href="/memories/${encodeURIComponent(detail.record_id)}">Open full memory →</a>`
      : '';
    const provenance = detail.provenance === 'ai_inferred'
      ? '<span class="badge badge-ai">AI-inferred</span>'
      : '<span class="badge badge-source">Source-grounded</span>';

    panelBody.innerHTML = `
      <p class="panel-eyebrow"><span class="cat-dot" style="background:${colorFor(detail)}"></span>${escapeHtml(detail.category)} ${provenance}</p>
      <h2 class="panel-title">${escapeHtml(detail.label)}</h2>
      ${detail.description ? `<p class="panel-desc">${escapeHtml(detail.description)}</p>` : ''}
      ${detail.occurred_at ? `<p class="panel-when">${escapeHtml(detail.occurred_at)}</p>` : ''}
      ${sourceMarkup(detail)}
      ${metaMarkup(detail)}
      ${record}
      ${neighborMarkup(detail)}
    `;

    panelBody.querySelectorAll('.node-link').forEach((btn) => {
      btn.addEventListener('click', () => {
        const target = Graph.graphData().nodes.find((n) => n.id === btn.dataset.id);
        selectNode(btn.dataset.id);
        if (target && target.x != null) {
          Graph.centerAt(target.x, target.y, 600);
          Graph.zoom(Math.max(Graph.zoom(), 2.2), 600);
        }
      });
    });
    panel.focus();
  }

  panelClose.addEventListener('click', clearSelection);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !panel.hidden) clearSelection();
  });

  // Respect reduced-motion: freeze the simulation quickly.
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  fetch('/graph.json')
    .then((res) => res.json())
    .then((data) => {
      sizeToContainer();
      if (!data.nodes.length) {
        emptyNote.hidden = false;
        return;
      }
      const categories = [...new Set(data.nodes.map((n) => n.category))].sort();
      buildLegend(categories);

      let didFit = false;
      Graph.onEngineStop(() => {
        if (!didFit) {
          Graph.zoomToFit(500, 60);
          didFit = true;
        }
      });
      if (reduceMotion) {
        Graph.cooldownTicks(0);
        Graph.d3AlphaDecay(0.2);
      }
      Graph.graphData({ nodes: data.nodes, links: data.edges });
      // Fallback fit in case the engine settles before the stop handler binds.
      setTimeout(() => { if (!didFit) { Graph.zoomToFit(500, 60); didFit = true; } }, 1500);
    })
    .catch(() => {
      emptyNote.hidden = false;
      emptyNote.textContent = 'Could not load the graph.';
    });
})();
