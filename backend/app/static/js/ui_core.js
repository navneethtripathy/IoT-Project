/* ==========================================================================
   CivicTwin-R — Shared UI Core Utilities
   Consistent navigation transitions, Chart.js Obsidian theme, SVG mark,
   safe HTML escaping, and accessible microinteractions.
   ========================================================================== */

(function (global) {
  'use strict';

  const OBSIDIAN_PALETTE = {
    bgPrimary: '#080B10',
    bgSecondary: '#0C1118',
    bgElevated: '#111821',
    bgInteractive: '#17212D',
    borderSubtle: '#253140',
    borderStrong: '#344050',
    textPrimary: '#F4F6F8',
    textSecondary: '#A0ADBD',
    textMuted: '#738196',
    glacier: '#62B5F5',
    teal: '#36C2C9',
    green: '#43C59E',
    amber: '#E9B65C',
    coral: '#F16D75',
  };

  function escapeHtml(raw) {
    if (raw === null || raw === undefined) return '';
    return String(raw)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function initScrollNav(navId) {
    const nav = document.getElementById(navId);
    if (!nav) return;
    const onScroll = () => {
      if (window.scrollY > 12) nav.classList.add('is-scrolled');
      else nav.classList.remove('is-scrolled');
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  function initRevealObserver() {
    const els = document.querySelectorAll('.ct-reveal');
    if (!els.length) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || typeof IntersectionObserver === 'undefined') {
      els.forEach((el) => el.classList.add('is-visible'));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08 }
    );
    els.forEach((el) => io.observe(el));
  }

  function configureChartDefaults(ChartLib) {
    if (!ChartLib || !ChartLib.defaults) return;
    ChartLib.defaults.color = OBSIDIAN_PALETTE.textSecondary;
    ChartLib.defaults.borderColor = '#19222E';
    ChartLib.defaults.font.family = '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif';
    ChartLib.defaults.font.size = 11;
    if (ChartLib.defaults.plugins && ChartLib.defaults.plugins.tooltip) {
      ChartLib.defaults.plugins.tooltip.backgroundColor = OBSIDIAN_PALETTE.bgElevated;
      ChartLib.defaults.plugins.tooltip.titleColor = OBSIDIAN_PALETTE.textPrimary;
      ChartLib.defaults.plugins.tooltip.bodyColor = OBSIDIAN_PALETTE.textSecondary;
      ChartLib.defaults.plugins.tooltip.borderColor = OBSIDIAN_PALETTE.borderStrong;
      ChartLib.defaults.plugins.tooltip.borderWidth = 1;
      ChartLib.defaults.plugins.tooltip.padding = 10;
      ChartLib.defaults.plugins.tooltip.cornerRadius = 6;
    }
  }

  async function copyTextWithFeedback(text, labelEl) {
    try {
      await navigator.clipboard.writeText(text);
      if (labelEl) {
        const orig = labelEl.innerText;
        labelEl.innerText = 'Copied';
        setTimeout(() => { labelEl.innerText = orig; }, 1400);
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  global.CivicTwinUI = {
    PALETTE: OBSIDIAN_PALETTE,
    escapeHtml,
    initScrollNav,
    initRevealObserver,
    configureChartDefaults,
    copyTextWithFeedback,
  };
})(window);
