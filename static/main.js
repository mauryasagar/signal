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
        const contentType = res.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
          throw new Error("Server timed out or returned an error. Please try again.");
        }

        let data;
        try {
          data = await res.json();
        } catch (e) {
          throw new Error("Server returned an invalid response. Please try again.");
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

// =========================================================
// DYNAMIC SCRIPT GENERATOR (Event Delegation for AJAX HTML)
// =========================================================
function initScriptGeneration() {
  document.addEventListener('click', async function (e) {
    const button = e.target.closest('.btn-script-gen');
    if (!button) return;

    e.preventDefault();

    const title = button.dataset.title;
    const angle = button.dataset.angle;
    const targetId = button.dataset.target;
    const outputDiv = document.getElementById(targetId);

    if (!outputDiv) return;

    // Update UI to loading state
    button.innerText = '🤖 Writing script...';
    button.disabled = true;
    button.style.opacity = '0.7';
    outputDiv.style.display = 'block';
    outputDiv.innerHTML = '<p style="color: #aaa;">Generating script, please wait...</p>';

    try {
      const response = await fetch('/generate_script', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title, angle: angle })
      });

      // Gracefully handle non-JSON server responses (like 502 gateways)
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        throw new Error("Server returned an error. Please try again.");
      }

      const data = await response.json();

      if (data.success) {
        const s = data.script;
        outputDiv.innerHTML = `
          <div style="margin-bottom: 15px;">
            <strong style="color: #e8a33d; display: block; margin-bottom: 4px;">🎬 Hook (0-15s)</strong>
            ${s.hook}
          </div>
          <div style="margin-bottom: 15px;">
            <strong style="color: #e8a33d; display: block; margin-bottom: 4px;">📺 Intro</strong>
            ${s.intro}
          </div>
          <div style="margin-bottom: 15px;">
            <strong style="color: #e8a33d; display: block; margin-bottom: 4px;">📝 Main Content</strong>
            <ul style="margin: 0; padding-left: 20px;">${s.body.map(item => `<li style="margin-bottom: 5px;">${item}</li>`).join('')}</ul>
          </div>
          <div style="margin-bottom: 15px;">
            <strong style="color: #e8a33d; display: block; margin-bottom: 4px;">🔚 Outro & CTA</strong>
            ${s.outro}
          </div>
          <div>
            <strong style="color: #e8a33d; display: block; margin-bottom: 4px;">🎥 B-Roll Ideas</strong>
            <ul style="margin: 0; padding-left: 20px;">${s.b_roll.map(item => `<li style="margin-bottom: 5px;">${item}</li>`).join('')}</ul>
          </div>
        `;
        button.innerText = '✓ Script Generated';
        button.style.opacity = '1';
      } else {
        outputDiv.innerHTML = `<p style="color: #ff4d4d;">Error: ${data.error}</p>`;
        button.innerText = 'Try Again';
        button.disabled = false;
        button.style.opacity = '1';
      }
    } catch (error) {
      outputDiv.innerHTML = `<p style="color: #ff4d4d;">Error: ${error.message}</p>`;
      button.innerText = 'Try Again';
      button.disabled = false;
      button.style.opacity = '1';
    }
  });
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
  initScriptGeneration(); // Initialize the new script generator listener
  initReportInteractions();

  const toggleBtn = document.getElementById("theme-toggle");
  if (toggleBtn) toggleBtn.addEventListener("click", toggleTheme);
});