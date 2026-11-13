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
  // Confirm dialogs name the exact platforms the user ticked, so the
  // confirmation states what will actually happen instead of a generic
  // "the selected platforms". The message lives on the button that was
  // clicked when a form has two actions (publish now vs schedule),
  // and on the form otherwise (the schedule cancel button). A form
  // with neither confirms nothing and submits plainly.
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var submitter = event.submitter;
      var message = null;
      if (submitter && submitter.getAttribute) {
        message = submitter.getAttribute("data-confirm");
      }
      if (!message) {
        message = form.getAttribute("data-confirm");
      }
      if (!message) {
        return;
      }
      var chosen = [];
      form.querySelectorAll("input[name='platforms']:checked").forEach(function (box) {
        chosen.push(box.value);
      });
      if (chosen.length && message.indexOf("the selected platforms") !== -1) {
        message = message.replace("the selected platforms", chosen.join(", "));
      }
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });
  // The "when" field belongs to scheduling only: it is required when
  // the Schedule button is clicked, and ignored when Publish now is
  // clicked. Without JavaScript the server still rejects an empty
  // schedule time with a plain-language error.
  document.querySelectorAll("form").forEach(function (form) {
    var when = form.querySelector("input[name='when']");
    if (!when) {
      return;
    }
    form.querySelectorAll("button[type='submit']").forEach(function (button) {
      button.addEventListener("click", function () {
        when.required = button.hasAttribute("data-require-when");
      });
    });
  });
  // Publish and schedule POSTs run server-side and can take a while
  // (slow platforms), during which the page otherwise showed nothing.
  // On submit, show a working state at once: the clicked button is
  // disabled (which also blocks an accidental double submit) and its
  // label switches to the progress text, with a status line under
  // the form that ticks up the elapsed seconds, so the wait feels
  // shorter than a frozen label. The progress text lives on the
  // button that was clicked when a form has two actions, and on the
  // form otherwise. If the confirm dialog cancelled the submit, this
  // handler sees the prevented event and leaves the form untouched.
  // No per-platform progress is shown: the server answers only when
  // every platform has finished, so any finer claim would be invented.
  // The ticker shows elapsed time only, never a fake percentage.
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (event.defaultPrevented) {
        return;
      }
      var submitter = event.submitter;
      var label = null;
      if (submitter && submitter.getAttribute) {
        label = submitter.getAttribute("data-progress");
      }
      if (!label) {
        label = form.getAttribute("data-progress");
      }
      if (!label) {
        return;
      }
      var button =
        submitter && submitter.tagName === "BUTTON"
          ? submitter
          : form.querySelector("button[type='submit']");
      if (button) {
        button.disabled = true;
        button.textContent = label;
      }
      var status = document.createElement("p");
      status.className = "dim";
      status.setAttribute("role", "status");
      var started = Date.now();
      var renderStatus = function () {
        var elapsed = Math.floor((Date.now() - started) / 1000);
        status.textContent =
          label + " " + elapsed + "s elapsed. This can take a while for slow platforms.";
      };
      renderStatus();
      form.appendChild(status);
      setInterval(renderStatus, 1000);
    });
  });
});
