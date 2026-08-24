(function () {
  var search = document.getElementById("recipe-search");
  var headerSearch = document.querySelector(".search-mini input[name='q']");
  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-tag-filter]"));
  var cards = Array.prototype.slice.call(document.querySelectorAll("[data-recipe-card]"));
  var empty = document.getElementById("recipe-empty");
  var count = document.getElementById("recipe-count");
  if (!cards.length) return;

  var activeTag = "";

  function norm(s) {
    return (s || "").toLowerCase();
  }

  function query() {
    if (search && search.value) return search.value;
    if (headerSearch && headerSearch.value) return headerSearch.value;
    return "";
  }

  function syncSearch(value) {
    if (search) search.value = value;
    if (headerSearch) headerSearch.value = value;
  }

  function apply() {
    var q = norm(query());
    var shown = 0;
    cards.forEach(function (card) {
      var hay = norm(card.getAttribute("data-title") + " " + card.getAttribute("data-tags") + " " + card.getAttribute("data-excerpt"));
      var tags = (card.getAttribute("data-tags") || "").split("|");
      var okQ = !q || hay.indexOf(q) !== -1;
      var okT = !activeTag || tags.indexOf(activeTag) !== -1;
      var on = okQ && okT;
      card.hidden = !on;
      if (on) shown += 1;
    });
    if (empty) empty.hidden = shown !== 0;
    if (count) count.textContent = shown + " recipe" + (shown === 1 ? "" : "s");
  }

  var params = new URLSearchParams(window.location.search);
  if (params.get("q")) syncSearch(params.get("q"));
  if (params.get("tag")) activeTag = params.get("tag");

  if (search) search.addEventListener("input", function () {
    if (headerSearch) headerSearch.value = search.value;
    apply();
  });
  if (headerSearch) {
    headerSearch.addEventListener("input", function () {
      if (search) search.value = headerSearch.value;
      apply();
    });
    var form = headerSearch.form;
    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if (search) search.value = headerSearch.value;
        apply();
        if (search) search.scrollIntoView({ block: "start", behavior: "smooth" });
      });
    }
  }

  chips.forEach(function (chip) {
    if (chip.getAttribute("data-tag-filter") === activeTag) chip.classList.add("is-on");
    chip.addEventListener("click", function () {
      var tag = chip.getAttribute("data-tag-filter") || "";
      if (tag === "" || activeTag === tag) {
        activeTag = "";
        chips.forEach(function (c) { c.classList.toggle("is-on", (c.getAttribute("data-tag-filter") || "") === ""); });
      } else {
        activeTag = tag;
        chips.forEach(function (c) { c.classList.toggle("is-on", c === chip); });
      }
      apply();
    });
  });

  apply();
})();
