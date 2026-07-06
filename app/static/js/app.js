// Smart Diet Planner — small, dependency-free UI behaviors.
// No framework needed: the app is server-rendered, so JS here only handles
// progressive-enhancement interactions (dismissible alerts, dynamic meal
// builder rows, photo preview) — never core functionality, so pages still
// work with JS disabled aside from those specific enhancements.

document.addEventListener('DOMContentLoaded', () => {
  initAlertDismiss();
  initPhotoDropzone();
});

function initAlertDismiss() {
  document.querySelectorAll('[data-alert-close]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const alertEl = btn.closest('.alert');
      if (alertEl) alertEl.remove();
    });
  });
}

function initPhotoDropzone() {
  const dropzone = document.getElementById('dropzone');
  if (!dropzone) return;

  const input = dropzone.querySelector('input[type="file"]');
  const preview = document.getElementById('photo-preview');
  const label = document.getElementById('dropzone-label');

  const showPreview = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      preview.src = e.target.result;
      preview.style.display = 'block';
      if (label) label.textContent = file.name;
    };
    reader.readAsDataURL(file);
  };

  dropzone.addEventListener('click', () => input.click());
  input.addEventListener('change', () => showPreview(input.files[0]));

  ['dragenter', 'dragover'].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    })
  );
  ['dragleave', 'drop'].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
    })
  );
  dropzone.addEventListener('drop', (e) => {
    const file = e.dataTransfer.files[0];
    if (file) {
      input.files = e.dataTransfer.files;
      showPreview(file);
    }
  });
}
