// Предпросмотр текстов, счётчик знаков, подстановки, подтверждения, загрузка файлов.
(function () {
  "use strict";
  var samples = window.SAMPLES || {};

  function render(text) {
    return text.replace(/\{\{|\}\}|\{(\w+)\}/g, function (m, name) {
      if (m === "{{") return "{";
      if (m === "}}") return "}";
      return Object.prototype.hasOwnProperty.call(samples, name) ? samples[name] : m;
    });
  }

  function autosize(el) {
    if (el.tagName !== "TEXTAREA") return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight + 2, 520) + "px";
  }

  document.querySelectorAll("[data-field]").forEach(function (form) {
    var input = form.querySelector(".js-text");
    if (!input) return;
    var preview = form.querySelector("[data-preview]");
    var count = form.querySelector(".count");
    var limit = count && count.dataset.limit ? parseInt(count.dataset.limit, 10) : 0;
    var initial = input.value;
    var draftKey = "draft:" + form.id;
    // сервер не принял правку: возвращаем то, что человек набрал
    try {
      var draft = sessionStorage.getItem(draftKey);
      if (draft !== null && form.querySelector(".field-err")) input.value = draft;
      else sessionStorage.removeItem(draftKey);
    } catch (e) { /* без sessionStorage просто теряем черновик */ }

    function update() {
      if (preview) preview.textContent = render(input.value);
      if (count) {
        count.textContent = limit ? input.value.length + " / " + limit : input.value.length + " знаков";
        count.classList.toggle("over", limit > 0 && input.value.length > limit);
      }
      form.classList.toggle("is-dirty", input.value !== initial);
      autosize(input);
    }
    input.addEventListener("input", update);
    input.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") form.requestSubmit();
    });
    form.addEventListener("submit", function () {
      try { sessionStorage.setItem(draftKey, input.value); } catch (e) { /* не страшно */ }
      initial = input.value;
      form.classList.remove("is-dirty");
    });
    form.querySelectorAll("[data-insert]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        var ins = chip.dataset.insert;
        var s = input.selectionStart, e = input.selectionEnd;
        input.value = input.value.slice(0, s) + ins + input.value.slice(e);
        input.focus();
        input.selectionStart = input.selectionEnd = s + ins.length;
        update();
      });
    });
    update();
  });

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-confirm]");
    if (btn && !window.confirm(btn.dataset.confirm)) e.preventDefault();
    if (e.target.closest("[data-open-side]")) document.body.classList.add("side-open");
    if (e.target.closest("[data-close-side]")) document.body.classList.remove("side-open");
  });

  document.querySelectorAll("[data-autosubmit]").forEach(function (input) {
    input.addEventListener("change", function () {
      if (!input.files.length) return;
      var form = input.form;
      var label = form.querySelector(".file span");
      if (label) label.textContent = "Загружаю…";
      form.classList.add("uploading");
      form.submit();
    });
  });

  window.addEventListener("beforeunload", function (e) {
    if (document.querySelector(".field.is-dirty")) { e.preventDefault(); e.returnValue = ""; }
  });
})();
