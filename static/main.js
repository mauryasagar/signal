// Theme management
function initTheme() {
  const stored = localStorage.getItem("theme");
  const theme = stored || "dark";
  document.documentElement.setAttribute("data-theme", theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
}

// Loading overlay with cycling status messages
const LOADING_MESSAGES = [
  "SCANNING TREND SIGNALS…",
  "CHECKING YOUTUBE DEMAND…",
  "RANKING BY DEMAND SCORE…",
  "DRAFTING TOPIC IDEAS…"
];

let _loadingInterval = null;

function showLoadingOverlay() {
  const overlay = document.getElementById("loading-overlay");
  const textEl = document.getElementById("loading-text");
  if (!overlay) return;

  overlay.classList.add("active");

  if (textEl) {
    if (_loadingInterval) clearInterval(_loadingInterval);
    let i = 0;
    textEl.textContent = LOADING_MESSAGES[0];
    textEl.style.opacity = "1";

    _loadingInterval = setInterval(function () {
      i = (i + 1) % LOADING_MESSAGES.length;
      textEl.style.opacity = "0";
      setTimeout(function () {
        textEl.textContent = LOADING_MESSAGES[i];
        textEl.style.opacity = "1";
      }, 150);
    }, 1200);
  }
}

function hideLoadingOverlay() {
  const overlay = document.getElementById("loading-overlay");
  if (overlay) overlay.classList.remove("active");
  if (_loadingInterval) clearInterval(_loadingInterval);
}

// Toast Notification System
function showToast(message) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = "toast-item";
  toast.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
    <span>${message}</span>
  `;
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add("show");
  });

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, 2400);
}

// Counter animation (0 -> target)
function animateCounters() {
  const counters = document.querySelectorAll("[data-count]");
  counters.forEach(el => {
    const target = parseInt(el.getAttribute("data-count"), 10);
    if (isNaN(target) || target <= 0) return;

    let current = 0;
    const duration = 800; // ms
    const startTime = performance.now();

    function step(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const ease = 1 - Math.pow(1 - progress, 3);
      current = Math.floor(ease * target);
      el.textContent = current.toLocaleString();

      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        el.textContent = target.toLocaleString();
      }
    }
    requestAnimationFrame(step);
  });
}

// Interactive Suggestion Chips & Preview Rows
function initSuggestionChips() {
  const chips = document.querySelectorAll(".chip, .preview-row");
  const input = document.getElementById("niche-input");
  const form = document.getElementById("search-form");

  chips.forEach(chip => {
    chip.addEventListener("click", () => {
      const niche = chip.getAttribute("data-niche");
      if (niche && input) {
        input.value = niche;
        input.focus();
        if (form) {
          form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
        }
      }
    });
  });
}

// Sample titles toggle accordion
function toggleSamples(btn) {
  const card = btn.closest(".topic-card");
  if (!card) return;
  const panel = card.querySelector(".sample-titles-panel");
  if (!panel) return;

  const isOpen = panel.style.display !== "none";
  if (isOpen) {
    panel.style.display = "none";
    btn.classList.remove("active");
  } else {
    panel.style.display = "block";
    btn.classList.add("active");
  }
}

// Topic Card Copy Buttons
function initCopyButtons() {
  document.addEventListener("click", function (e) {
    const copyBtn = e.target.closest(".copy-topic-btn");
    if (copyBtn) {
      const textToCopy = copyBtn.getAttribute("data-text");
      if (textToCopy) {
        navigator.clipboard.writeText(textToCopy).then(() => {
          showToast("Copied title to clipboard!");
        }).catch(() => {
          showToast("Failed to copy title.");
        });
      }
    }

    const copyAllBtn = e.target.closest("#copy-all-btn");
    if (copyAllBtn) {
      const cards = document.querySelectorAll(".topic-card h4");
      const titles = Array.from(cards).map((h, i) => `${i + 1}. ${h.textContent.trim()}`).join("\n");
      if (titles) {
        navigator.clipboard.writeText(titles).then(() => {
          showToast("Copied all topic titles!");
        });
      }
    }
  });
}

// Real-Time Topic Filter Search
function initTopicFilter() {
  const filterInput = document.getElementById("topic-filter-input");
  if (!filterInput) return;

  filterInput.addEventListener("input", function () {
    const q = this.value.toLowerCase().trim();
    const cards = document.querySelectorAll(".topic-card");
    let visibleCount = 0;

    cards.forEach(card => {
      const title = card.getAttribute("data-title") || "";
      const query = card.getAttribute("data-query") || "";
      const angle = card.getAttribute("data-angle") || "";

      if (!q || title.includes(q) || query.includes(q) || angle.includes(q)) {
        card.style.display = "grid";
        visibleCount++;
      } else {
        card.style.display = "none";
      }
    });

    const noResults = document.getElementById("no-topics-found");
    if (noResults) {
      noResults.style.display = (visibleCount === 0 && q.length > 0) ? "block" : "none";
    }
  });
}

// Async Form Submission (Single-Page Dynamic Swap)
function initAsyncFormSubmit() {
  const form = document.getElementById("search-form");
  if (!form) return;

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const input = document.getElementById("niche-input") || form.querySelector('input[name="niche"]');
    if (!input || !input.value.trim()) return;

    const niche = input.value.trim();
    showLoadingOverlay();

    fetch(form.action, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({ niche: niche })
    })
      .then(async res => {
        let data;
        try {
          data = await res.json();
        } catch (e) {
          throw new Error("Server returned an invalid HTML response instead of JSON. Please try again.");
        }

        if (!res.ok) {
          throw new Error(data.error || "Generation failed.");
        }
        return data;
      })
      .then(data => {
        hideLoadingOverlay();
        if (data.success && data.html) {
          // Parse returned report HTML and inject cleanly
          const parser = new DOMParser();
          const doc = parser.parseFromString(data.html, "text/html");
          const newContent = doc.getElementById("dynamic-content-area");
          const targetArea = document.getElementById("dynamic-content-area");

          if (newContent && targetArea) {
            targetArea.style.opacity = "0";
            setTimeout(() => {
              targetArea.innerHTML = newContent.innerHTML;
              targetArea.style.opacity = "1";
              window.scrollTo({ top: 0, behavior: "smooth" });

              // Re-bind interactive handlers for newly injected content
              initReportInteractions();
            }, 180);
          } else {
            window.location.reload();
          }
        }
      })
      .catch(err => {
        hideLoadingOverlay();
        const errContainer = document.getElementById("error-banner-container");
        if (errContainer) {
          errContainer.innerHTML = `<div class="error-banner">${err.message || "An unexpected error occurred."}</div>`;
        } else {
          alert(err.message);
        }
      });
  });
}

// FAQ Accordion Handler
function toggleFaq(btn) {
  const item = btn.closest(".faq-item");
  if (!item) return;
  const answer = item.querySelector(".faq-answer");
  if (!answer) return;

  const isOpen = answer.style.display === "block";
  if (isOpen) {
    answer.style.display = "none";
    btn.classList.remove("active");
  } else {
    answer.style.display = "block";
    btn.classList.add("active");
  }
}

function initReportInteractions() {
  // Only run on pages that have report-specific elements
  if (document.querySelector('[data-count]')) animateCounters();
  if (document.getElementById('topic-filter-input')) initTopicFilter();
  initSuggestionChips();
}

document.addEventListener("DOMContentLoaded", function () {
  initTheme();
  initAsyncFormSubmit();
  initSuggestionChips();
  initCopyButtons();
  initReportInteractions();

  const toggleBtn = document.getElementById("theme-toggle");
  if (toggleBtn) toggleBtn.addEventListener("click", toggleTheme);
});

