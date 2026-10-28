# Knowledge presentation builder

Build a presentation that explains a body of knowledge **and how its parts connect**. I will paste a Second Brain graph export (a schema-2.0 JSON object of `nodes` and `edges`) after the divider — export it from the app's graph view with "Export JSON".

## Pick one output format

Produce exactly one of these, matching the format I ask for (default: **single-page HTML**):

- **Single-page HTML** — one self-contained `.html` file: all CSS and JS inline, **no external resources or CDN links**, works offline by opening the file. A horizontal/scrollable slide deck or a clean scrollable narrative. If you draw the graph, use inline SVG or a `<canvas>` with vanilla JS; do not load a library.
- **PPTX** — a complete, runnable Python script using `python-pptx` that generates the `.pptx`, one slide per section below. Include the full script, ready to run.
- **PDF** — a print-ready single-page HTML document (A4/Letter, `@media print` styles, page breaks) that I can open and "Print to PDF", or, if I ask, a complete LaTeX source.

## Build it only from the graph — do not invent

- Use only the nodes, edges, labels, descriptions, timestamps, and sources in the pasted JSON. Never add facts, people, or relationships that are not in the data.
- When a node or edge is marked `"provenance": "ai_inferred"`, present it as an inferred connection, visually distinct from source-grounded ones. Preserve the distinction between what the sources stated and what was inferred.
- Where a node carries a `source`, you may cite it.

## Structure

1. **Title & overview** — what this knowledge map covers, and counts (nodes, edges, categories).
2. **The map** — a visual of the graph or its main clusters, with a category legend/colour key.
3. **Key entities** — the most connected nodes (hubs), each with its description and what it links to.
4. **Clusters & themes** — groups of related nodes and what ties each group together.
5. **Relationships that matter** — the most important edges, read as sentences ("X leads Y", "A depends on B"), separating source-grounded from AI-inferred.
6. **Timeline** — any time-anchored nodes (events, memories) in order.
7. **Open threads** — gaps or sparsely connected nodes worth following up.

Keep it legible and self-contained. Prefer clarity over decoration.

Graph export (schema-2.0 JSON) begins after this line:

---
