/* Young Engineers — scripts du site public (aucun script inline : compatible CSP) */
(function () {
  "use strict";

  // Menu mobile
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a") && nav.classList.contains("open")) {
        nav.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  // Apparition douce des sections (sans JS : tout reste visible)
  var items = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && items.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    items.forEach(function (el) { io.observe(el); });
  } else {
    items.forEach(function (el) { el.classList.add("in"); });
  }

  // Formulaire de préinscription : messages de validation traduits
  var form = document.getElementById("prereg-form");
  if (form) {
    var msg = {
      required: form.dataset.msgRequired,
      email: form.dataset.msgEmail,
      phone: form.dataset.msgPhone
    };
    var fields = form.querySelectorAll("input, select, textarea");
    fields.forEach(function (el) {
      el.addEventListener("invalid", function () {
        var v = el.validity;
        if (v.valueMissing) { el.setCustomValidity(msg.required); }
        else if (v.typeMismatch) { el.setCustomValidity(msg.email); }
        else if (v.patternMismatch) { el.setCustomValidity(msg.phone); }
        else if (v.tooShort || v.tooLong || v.rangeUnderflow || v.rangeOverflow) { el.setCustomValidity(msg.required); }
      });
      var reset = function () { el.setCustomValidity(""); };
      el.addEventListener("input", reset);
      el.addEventListener("change", reset);
    });

    // Les cases « centres d'intérêt » : au moins une
    var boxes = form.querySelectorAll('input[name="interests"]');
    var syncBoxes = function () {
      var any = Array.prototype.some.call(boxes, function (b) { return b.checked; });
      boxes.forEach(function (b, i) { b.required = !any && i === 0; });
    };
    boxes.forEach(function (b) { b.addEventListener("change", syncBoxes); });
    syncBoxes();

    // Anti double envoi
    form.addEventListener("submit", function () {
      var btn = form.querySelector('button[type="submit"]');
      if (btn && form.checkValidity()) {
        btn.disabled = true;
        btn.textContent = form.dataset.msgSending || btn.textContent;
      }
    });

    var summary = document.getElementById("error-summary");
    if (summary) { summary.focus(); }
  }
})();
