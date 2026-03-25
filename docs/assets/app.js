
function initSearch() {
  const input = document.getElementById("global-search");
  const results = document.getElementById("search-results");
  const payload = document.getElementById("search-data");
  if (!input || !results || !payload) return;
  const items = JSON.parse(payload.textContent);

  const render = (query) => {
    const value = query.trim().toLowerCase();
    if (!value) {
      results.innerHTML = "";
      return;
    }
    const matches = items
      .filter((item) => `${item.number} ${item.theme} ${item.summary}`.toLowerCase().includes(value))
      .slice(0, 12);

    results.innerHTML = matches.length
      ? matches.map((item) => `
          <a class="search-result" href="${item.url}">
            <strong>${item.number} · ${item.theme}</strong>
            <span>${item.year_bucket} · ${item.lang}</span>
            <p>${item.summary}</p>
          </a>
        `).join("")
      : `<div class="search-result"><strong>没有匹配结果</strong><span>请尝试更短的关键词或案件编号。</span></div>`;
  };

  input.addEventListener("input", (event) => render(event.target.value));
}

function initTableSearch() {
  document.querySelectorAll(".table-search").forEach((input) => {
    const table = input.closest(".year-directory")?.querySelector("tbody");
    if (!table) return;
    const rows = Array.from(table.querySelectorAll("tr"));
    input.addEventListener("input", (event) => {
      const value = event.target.value.trim().toLowerCase();
      rows.forEach((row) => {
        const haystack = row.dataset.search || row.textContent.toLowerCase();
        row.hidden = value ? !haystack.includes(value) : false;
      });
    });
  });
}

initSearch();
initTableSearch();
