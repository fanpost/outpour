// Outpour web UI: small progressive enhancements only. Every action
// also works with JavaScript disabled, because the forms post normally.
document.addEventListener("DOMContentLoaded", function () {
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
