/* ============================================================
   LUXA — Vendor JS
   Place at: MAIN/static/MAIN/js/vendor.js
   ============================================================ */

(function () {
  'use strict';

  // ── Product Management: filter chips ──
  const filterChips = document.querySelectorAll('[data-filter]');
  filterChips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      const filter = this.dataset.filter;

      // Update active chip UI
      filterChips.forEach(c => c.classList.remove('active'));
      this.classList.add('active');

      // Filter table rows (desktop)
      const tableRows = document.querySelectorAll('#productsTable tbody tr[data-status]');
      tableRows.forEach(function (row) {
        if (filter === 'all' || row.dataset.status === filter) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });

      // Filter mobile cards
      const mobileCards = document.querySelectorAll('.mobile-product-card[data-status]');
      mobileCards.forEach(function (card) {
        if (filter === 'all' || card.dataset.status === filter) {
          card.style.display = '';
        } else {
          card.style.display = 'none';
        }
      });
    });
  });

  // ── Select all checkbox ──
  const selectAll = document.getElementById('selectAll');
  if (selectAll) {
    selectAll.addEventListener('change', function () {
      document.querySelectorAll('.row-check').forEach(cb => {
        cb.checked = this.checked;
      });
    });
  }

  // ── Product search (client-side filter) ──
  const searchInput = document.getElementById('pmSearch');
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      const query = this.value.toLowerCase().trim();

      // Desktop table rows
      document.querySelectorAll('#productsTable tbody tr').forEach(function (row) {
        const name = row.querySelector('.pm-product-name')?.textContent.toLowerCase() || '';
        const cat  = row.querySelector('.pm-product-category')?.textContent.toLowerCase() || '';
        row.style.display = (name.includes(query) || cat.includes(query)) ? '' : 'none';
      });

      // Mobile cards
      document.querySelectorAll('.mobile-product-card').forEach(function (card) {
        const name = card.querySelector('.mobile-product-card__name')?.textContent.toLowerCase() || '';
        card.style.display = name.includes(query) ? '' : 'none';
      });
    });
  }

  // ── Photo upload drag & drop ──
  const dropZone = document.getElementById('dropZone');
  const galleryInput = document.getElementById('galleryInput');
  const galleryThumbs = document.getElementById('galleryThumbs');

  if (dropZone && galleryInput) {
    ['dragenter', 'dragover'].forEach(evt => {
      dropZone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropZone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(evt => {
      dropZone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropZone.classList.remove('dragover');
      });
    });

    dropZone.addEventListener('drop', function (e) {
      const files = e.dataTransfer.files;
      handleFilePreview(files);
    });

    galleryInput.addEventListener('change', function () {
      handleFilePreview(this.files);
    });
  }

  function handleFilePreview(files) {
    if (!galleryThumbs) return;
    Array.from(files).slice(0, 10).forEach(function (file) {
      if (!file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = function (e) {
        const addBtn = galleryThumbs.querySelector('.photo-thumb--add');
        const thumb = document.createElement('div');
        thumb.className = 'photo-thumb';
        thumb.innerHTML = `
          <img src="${e.target.result}" alt="Upload preview" />
          <button class="photo-thumb__remove" type="button" title="Remove">
            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" fill="none" viewBox="0 0 24 24" stroke-width="3" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        `;
        thumb.querySelector('.photo-thumb__remove').addEventListener('click', () => thumb.remove());
        if (addBtn) {
          galleryThumbs.insertBefore(thumb, addBtn);
        } else {
          galleryThumbs.appendChild(thumb);
        }
      };
      reader.readAsDataURL(file);
    });
  }

  // ── 3D view slot click handlers ──
  document.querySelectorAll('.model-view-slot').forEach(function (slot) {
    const fileInput = slot.querySelector('input[type="file"]');
    if (fileInput) {
      fileInput.addEventListener('change', function () {
        if (this.files[0]) {
          const reader = new FileReader();
          reader.onload = function (e) {
            slot.classList.add('model-view-slot--done');
            slot.innerHTML = `
              <div class="model-view-slot__check">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="3" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5"/>
                </svg>
              </div>
              <img src="${e.target.result}" alt="3D view" style="position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;border-radius:var(--r-md);" />
              <p class="model-view-slot__label" style="z-index:1;">${slot.dataset.view || ''}</p>
              <p class="model-view-slot__status" style="z-index:1;">Uploaded ✓</p>
            `;
          };
          reader.readAsDataURL(this.files[0]);
          updateCompletionBar();
        }
      });
    }
  });

  function updateCompletionBar() {
    const total = document.querySelectorAll('.model-view-slot').length;
    const done  = document.querySelectorAll('.model-view-slot--done').length;
    const fill  = document.querySelector('.completion-bar-fill');
    const label = document.querySelector('.completion-bar-top span:last-child');
    if (fill) fill.style.width = `${(done / total) * 100}%`;
    if (label) label.textContent = `${done} / ${total} views uploaded`;
  }

  // ── Bulk actions dropdown ──
  const bulkBtn = document.getElementById('bulkActionsBtn');
  if (bulkBtn) {
    bulkBtn.addEventListener('click', function () {
      const checked = document.querySelectorAll('.row-check:checked');
      if (checked.length === 0) {
        alert('Please select at least one product.');
        return;
      }
      // Implement bulk action UI as needed
    });
  }

})();
