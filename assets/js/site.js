(function () {
  var search = document.getElementById("recipe-search");
  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-tag-filter]"));
  var cards = Array.prototype.slice.call(document.querySelectorAll("[data-recipe-card]"));
  var empty = document.getElementById("recipe-empty");
  var count = document.getElementById("recipe-count");
  if (!cards.length) return;

  var activeTag = "";

  function norm(s) {
    return (s || "").toLowerCase();
  }

  function apply() {
    var q = search ? norm(search.value) : "";
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

  if (search) {
    var params = new URLSearchParams(window.location.search);
    if (params.get("q")) search.value = params.get("q");
    if (params.get("tag")) activeTag = params.get("tag");
    search.addEventListener("input", apply);
  }

  chips.forEach(function (chip) {
    if (chip.getAttribute("data-tag-filter") === activeTag) chip.classList.add("is-on");
    chip.addEventListener("click", function () {
      var tag = chip.getAttribute("data-tag-filter");
      if (activeTag === tag) {
        activeTag = "";
        chip.classList.remove("is-on");
      } else {
        activeTag = tag;
        chips.forEach(function (c) { c.classList.toggle("is-on", c === chip); });
      }
      apply();
    });
  });

  apply();
})();
