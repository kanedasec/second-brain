(() => {
  const cards = document.querySelectorAll('[data-prompt-id]');
  if (!cards.length) return;

  const LANG = document.documentElement.lang || 'en';
  const STR = {
    'pt-BR': {
      'Reveal prompt': 'Revelar prompt',
      'Hide': 'Ocultar',
      'Copy': 'Copiar',
      'Copied': 'Copiado',
      'Loading…': 'Carregando…',
      'Could not load this prompt.': 'Não foi possível carregar este prompt.',
    },
  };
  const tr = (s) => (STR[LANG] && STR[LANG][s]) || s;

  cards.forEach((card) => {
    const id = card.dataset.promptId;
    const revealBtn = card.querySelector('[data-reveal]');
    const copyBtn = card.querySelector('[data-copy]');
    const region = card.querySelector('.prompt-reveal');
    const code = card.querySelector('code');
    let loaded = false;

    revealBtn?.addEventListener('click', async () => {
      const opening = region.hidden;
      if (opening) {
        region.hidden = false;
        revealBtn.setAttribute('aria-expanded', 'true');
        revealBtn.textContent = tr('Hide');
        if (copyBtn) copyBtn.hidden = false;
        if (!loaded) {
          code.textContent = tr('Loading…');
          try {
            const res = await fetch(`/prompts/${encodeURIComponent(id)}.txt`);
            if (!res.ok) throw new Error('load failed');
            code.textContent = await res.text();
            loaded = true;
          } catch {
            code.textContent = tr('Could not load this prompt.');
          }
        }
      } else {
        region.hidden = true;
        revealBtn.setAttribute('aria-expanded', 'false');
        revealBtn.textContent = tr('Reveal prompt');
        if (copyBtn) copyBtn.hidden = true;
      }
    });

    copyBtn?.addEventListener('click', async () => {
      if (!loaded) return;
      try {
        await navigator.clipboard.writeText(code.textContent);
        const previous = copyBtn.textContent;
        copyBtn.textContent = tr('Copied');
        setTimeout(() => { copyBtn.textContent = previous; }, 1600);
      } catch {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(code);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    });
  });
})();
