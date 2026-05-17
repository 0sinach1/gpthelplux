/* ============================================================
   LUXA — Navbar JS
   Place at: MAIN/static/MAIN/js/navbar.js
   ============================================================ */

(function () {
  'use strict';

  // ── Mobile menu toggle ──
  const hamburger = document.getElementById('mobileMenuBtn');
  const mobileSearch = document.querySelector('.mobile-search-bar');

  if (hamburger) {
    hamburger.addEventListener('click', function () {
      const expanded = this.getAttribute('aria-expanded') === 'true';
      this.setAttribute('aria-expanded', String(!expanded));
      this.classList.toggle('is-open');
      // You can implement a slide-out drawer here if needed
    });
  }

  // ── Keyboard accessibility for navbar user dropdown ──
  const navUser = document.querySelector('.navbar-user');
  if (navUser) {
    navUser.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const dropdown = this.querySelector('.navbar-dropdown');
        if (dropdown) {
          const isVisible = dropdown.style.visibility === 'visible' ||
            getComputedStyle(dropdown).visibility === 'visible';
          dropdown.style.visibility = isVisible ? 'hidden' : 'visible';
          dropdown.style.opacity   = isVisible ? '0' : '1';
        }
      }
      if (e.key === 'Escape') {
        const dropdown = this.querySelector('.navbar-dropdown');
        if (dropdown) {
          dropdown.style.visibility = 'hidden';
          dropdown.style.opacity = '0';
        }
      }
    });

    // Close on outside click
    document.addEventListener('click', function (e) {
      if (!navUser.contains(e.target)) {
        const dropdown = navUser.querySelector('.navbar-dropdown');
        if (dropdown) {
          dropdown.style.visibility = 'hidden';
          dropdown.style.opacity = '0';
        }
      }
    });
  }

  // ── Auto-hide navbar on scroll down, show on scroll up ──
  let lastScrollY = window.scrollY;
  const navbar = document.querySelector('.luxa-navbar');

  if (navbar) {
    window.addEventListener('scroll', function () {
      const currentY = window.scrollY;
      if (currentY > lastScrollY && currentY > 80) {
        navbar.style.transform = 'translateY(-100%)';
      } else {
        navbar.style.transform = 'translateY(0)';
      }
      lastScrollY = currentY;
    }, { passive: true });
    navbar.style.transition = 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
  }

  // ── Django messages auto-dismiss ──
  const messages = document.querySelectorAll('.messages-list li');
  messages.forEach(function (msg) {
    setTimeout(function () {
      msg.style.opacity = '0';
      msg.style.transform = 'translateY(-4px)';
      msg.style.transition = 'all 0.3s ease';
      setTimeout(() => msg.remove(), 300);
    }, 4000);
  });

})();
