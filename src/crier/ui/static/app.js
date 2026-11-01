// Outpour web UI: small progressive enhancements only. Every action
// also works with JavaScript disabled, because the forms post normally.
document.addEventListener("DOMContentLoaded", function () {
  // Dark mode: the head script has already applied the saved theme
  // (localStorage "outpour-theme") to <html data-theme> before first
  // paint; this wires the toggle button and keeps its label honest.
  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    var syncLabel = function () {
      toggle.textContent =
        document.documentElement.dataset.theme === "dark" ? "Light mode" : "Dark mode";
    };
    syncLabel();
    toggle.addEventListener("click", function () {
      var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem("outpour-theme", next);
      } catch (e) {}
      syncLabel();
    });
  }
  // Editor status line: filename, live word count, characters, and
  // reading time, in the vim-status-line spirit. The server renders
  // the initial values; this keeps them honest while typing.
  var area = document.querySelector("textarea[name='body']");
  var status = document.getElementById("editor-status");
  if (area && status) {
    var fileName = status.getAttribute("data-name") || "";
    var renderStatus = function () {
      var trimmed = area.value.trim();
      var words = trimmed ? trimmed.split(/\s+/).length : 0;
      var parts = [];
      if (fileName) {
        parts.push(fileName);
      }
      parts.push(words + " words");
      parts.push(area.value.length + " characters");
      if (words) {
        parts.push(Math.max(1, Math.round(words / 200)) + " min read");
      }
      status.textContent = parts.join(" · ");
    };
    area.addEventListener("input", renderStatus);
    renderStatus();
  }
  // Focus mode: dim everything around the editor while writing. The
  // toggle itself and the Save button stay bright so the way out and
  // the way to save are never hidden.
  var focusToggle = document.getElementById("focus-toggle");
  if (focusToggle) {
    focusToggle.addEventListener("click", function () {
      var on = document.body.classList.toggle("focus");
      focusToggle.textContent = on ? "Exit focus" : "Focus mode";
    });
  }
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });
  // Publish and schedule POSTs run server-side and can take a while
  // (slow platforms), during which the page otherwise showed nothing.
  // On submit, show a working state at once: the button is disabled
  // (which also blocks an accidental double submit) and its label
  // switches to the form's progress text, with a status line under
  // the form. If the confirm dialog cancelled the submit, this
  // handler sees the prevented event and leaves the form untouched.
  // No per-platform progress is shown: the server answers only when
  // every platform has finished, so any finer claim would be invented.
  document.querySelectorAll("form[data-progress]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (event.defaultPrevented) {
        return;
      }
      var label = form.getAttribute("data-progress") || "Working...";
      var button = form.querySelector("button[type='submit']");
      if (button) {
        button.disabled = true;
        button.textContent = label;
      }
      var status = document.createElement("p");
      status.className = "dim";
      status.setAttribute("role", "status");
      status.textContent = label + " This can take a while for slow platforms.";
      form.appendChild(status);
    });
  });
});
