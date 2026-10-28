(() => {
  const navToggle = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.primary-nav');
  navToggle?.addEventListener('click', () => {
    const open = nav?.classList.toggle('is-open') ?? false;
    navToggle.setAttribute('aria-expanded', String(open));
  });

  const search = document.querySelector('#q');
  document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
      event.preventDefault();
      search?.focus();
    }
  });

  const fileInput = document.querySelector('#files');
  const fileList = document.querySelector('#file-list');
  const dropZone = document.querySelector('.drop-zone');
  const showFiles = () => {
    if (!fileList || !fileInput) return;
    fileList.replaceChildren(...Array.from(fileInput.files ?? []).map((file) => {
      const item = document.createElement('span');
      item.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
      return item;
    }));
  };
  fileInput?.addEventListener('change', showFiles);
  ['dragenter', 'dragover'].forEach((name) => dropZone?.addEventListener(name, () => dropZone.classList.add('is-dragging')));
  ['dragleave', 'drop'].forEach((name) => dropZone?.addEventListener(name, () => dropZone.classList.remove('is-dragging')));

  const copyButton = document.querySelector('#copy-prompt');
  copyButton?.addEventListener('click', async () => {
    const target = document.getElementById(copyButton.dataset.copyTarget);
    if (!target) return;
    try {
      await navigator.clipboard.writeText(target.textContent);
      const previous = copyButton.textContent;
      copyButton.textContent = 'Copied';
      setTimeout(() => { copyButton.textContent = previous; }, 1800);
    } catch {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(target);
      selection.removeAllRanges();
      selection.addRange(range);
      copyButton.textContent = 'Select & copy';
    }
  });
})();
