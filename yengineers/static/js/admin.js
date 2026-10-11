/* Administration : empêche le double envoi des formulaires. */
(function () {
  "use strict";
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector('button[type="submit"]');
      if (btn && form.checkValidity()) {
        setTimeout(function () { btn.disabled = true; }, 0);
      }
    });
  });
})();
