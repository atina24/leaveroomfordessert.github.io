(function () {
  var btn = document.querySelector(".header-collapse");
  if (!btn) return;

  var STORAGE_KEY = "lrfd.headerHidden";

  function apply(hidden, save) {
    document.body.classList.toggle("header-collapsed", hidden);
    btn.setAttribute("aria-expanded", hidden ? "false" : "true");
    btn.setAttribute("aria-label", hidden ? "Show header" : "Hide header");
    if (save) {
      try { localStorage.setItem(STORAGE_KEY, hidden ? "1" : "0"); } catch (e) {}
    }
  }

  try {
    apply(localStorage.getItem(STORAGE_KEY) === "1", false);
  } catch (e) {}

  btn.addEventListener("click", function () {
    apply(!document.body.classList.contains("header-collapsed"), true);
  });
})();