let allResults = [];
let catalogData = null;
let priceDebounce = null;

const searchForm = document.getElementById("search-form");
const zipInput = document.getElementById("zip-input");
const searchBtn = document.getElementById("search-btn");
const catalogSummary = document.getElementById("catalog-summary");
const controlsPanel = document.getElementById("controls-panel");
const serviceFilter = document.getElementById("service-filter");
const maxPriceFilter = document.getElementById("max-price-filter");
const sortBy = document.getElementById("sort-by");
const resultsPanel = document.getElementById("results-panel");
const resultsTitle = document.getElementById("results-title");
const resultsCount = document.getElementById("results-count");
const statusMessage = document.getElementById("status-message");

const tabSearch = document.getElementById("tab-search");
const tabZips = document.getElementById("tab-zips");
const viewSearch = document.getElementById("view-search");
const viewZips = document.getElementById("view-zips");
const zipTbody = document.getElementById("zip-tbody");
const zipCountBadge = document.getElementById("zip-count-badge");
const zipLimitSelect = document.getElementById("zip-limit-select");

searchForm.addEventListener("submit", runSearch);
serviceFilter.addEventListener("change", () => runSearch());
maxPriceFilter.addEventListener("input", () => {
  clearTimeout(priceDebounce);
  priceDebounce = setTimeout(() => runSearch(), 350);
});
sortBy.addEventListener("change", renderResults);
zipLimitSelect.addEventListener("change", renderZipTable);

tabSearch.addEventListener("click", () => switchTab("search"));
tabZips.addEventListener("click", () => switchTab("zips"));

loadCatalogSummary();

function switchTab(tab) {
  if (tab === "search") {
    tabSearch.classList.add("active");
    tabZips.classList.remove("active");
    viewSearch.classList.remove("hidden");
    viewZips.classList.add("hidden");
  } else {
    tabZips.classList.add("active");
    tabSearch.classList.remove("active");
    viewZips.classList.remove("hidden");
    viewSearch.classList.add("hidden");
    renderZipTable();
  }
}

async function loadCatalogSummary() {
  try {
    const response = await fetch("/api/catalog");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Catalog is unavailable");
    catalogData = data;
    catalogSummary.textContent = `${data.listing_count} listings across ${data.zip_count} ZIP codes.`;
    buildServiceFilter(data.service_types || []);
    renderZipTable();
  } catch (error) {
    catalogSummary.textContent = error.message;
  }
}

function buildServiceFilter(services) {
  const current = serviceFilter.value;
  const sorted = [...new Set(services)].sort();
  serviceFilter.innerHTML = '<option value="">All services</option>' + sorted.map(service =>
    `<option value="${escapeAttr(service)}">${escapeHtml(service)}</option>`
  ).join("");
  if (sorted.includes(current)) serviceFilter.value = current;
}

function renderZipTable() {
  if (!catalogData || !catalogData.zip_codes) return;
  let zips = [...catalogData.zip_codes];
  zips.sort((a, b) => String(a.zip_code).localeCompare(String(b.zip_code)));
  const limitVal = zipLimitSelect.value;
  const totalCount = zips.length;
  if (limitVal !== "all") {
    const limitNum = parseInt(limitVal, 10) || 100;
    zips = zips.slice(0, limitNum);
  }
  zipCountBadge.textContent = `Showing ${zips.length} of ${totalCount} ZIP codes`;
  zipTbody.innerHTML = zips.map(row => `
    <tr>
      <td><strong>${escapeHtml(row.zip_code)}</strong></td>
      <td>${escapeHtml(row.city)}</td>
      <td>${escapeHtml(row.state)}</td>
      <td>${escapeHtml(row.listing_count)}</td>
      <td>${escapeHtml(row.services)}</td>
      <td><button class="action-link" type="button" onclick="searchZip('${escapeAttr(row.zip_code)}')">View Services</button></td>
    </tr>
  `).join("");
}

window.searchZip = function(zipCode) {
  zipInput.value = zipCode;
  serviceFilter.value = "";
  maxPriceFilter.value = "";
  sortBy.value = "relevance";
  switchTab("search");
  runSearch();
};

async function runSearch(event) {
  if (event) event.preventDefault();
  if (!searchForm.reportValidity()) return;

  const zipCode = zipInput.value.trim();
  const serviceType = serviceFilter.value.trim();
  const maxPriceRaw = maxPriceFilter.value.trim();

  searchBtn.disabled = true;
  statusMessage.textContent = "Searching the local catalog…";

  try {
    const payload = { zip_code: zipCode };
    if (serviceType) payload.service_type = serviceType;
    if (maxPriceRaw !== "") payload.max_price = maxPriceRaw;

    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Search failed");

    allResults = data.results || [];
    resultsTitle.textContent = serviceType
      ? `${serviceType} in ${zipCode}`
      : `Services in ${zipCode}`;
    controlsPanel.classList.remove("hidden");
    renderResults();
    statusMessage.textContent = allResults.length
      ? ""
      : `No listings matched ${zipCode}${serviceType ? " for " + serviceType : ""}.`;
  } catch (error) {
    allResults = [];
    controlsPanel.classList.add("hidden");
    resultsPanel.innerHTML = "";
    statusMessage.textContent = error.message;
  } finally {
    searchBtn.disabled = false;
  }
}

function renderResults() {
  const sorted = [...allResults];
  sorted.sort((a, b) => compareRows(a, b, sortBy.value));
  resultsCount.textContent = `${sorted.length} ${sorted.length === 1 ? "listing" : "listings"}`;
  resultsPanel.innerHTML = sorted.map(renderCard).join("");
}

function compareRows(a, b, sort) {
  if (sort === "rating") return numberDescending(a.rating, b.rating);
  if (sort === "reviews") return numberDescending(a.review_count, b.review_count);
  if (sort === "price") return numberAscending(a.price_usd, b.price_usd);
  if (sort === "provider") return a.provider_name.localeCompare(b.provider_name);
  return numberDescending(a.rating, b.rating) ||
    numberDescending(a.review_count, b.review_count);
}

function numberDescending(a, b) {
  return (b ?? -Infinity) - (a ?? -Infinity);
}

function numberAscending(a, b) {
  return (a ?? Infinity) - (b ?? Infinity);
}

function renderCard(row) {
  const profileLink = row.profile_url
    ? `<a href="${escapeAttr(row.profile_url)}" target="_blank" rel="noopener noreferrer">Contact</a>`
    : "";
  const rating = row.rating === null
    ? "Not rated"
    : `★ ${formatNumber(row.rating)} · ${row.review_count ?? 0} reviews`;
  const rate = row.price_usd === null
    ? "Rate unavailable"
    : `$${formatNumber(row.price_usd)} ${escapeHtml(row.price_unit)}`;

  return `
    <article class="result-card">
      <div class="card-top">
        <div class="result-topline">
          <span class="service-pill">${escapeHtml(row.service_type)}</span>
          <span class="source">${escapeHtml(row.source)}</span>
        </div>
        <h3>${escapeHtml(row.provider_name)}</h3>
        <p class="location">${escapeHtml(row.city)}, ${escapeHtml(row.state)} ${escapeHtml(row.zip_code)}</p>
      </div>
      <div class="card-body">
        <p class="result-description">${escapeHtml(row.description || "No description provided.")}</p>
        <div class="expanded-details">
          <p class="pet-types">Pets: ${escapeHtml(row.pet_types || "Not listed")}</p>
          ${profileLink ? `<div class="profile">${profileLink}</div>` : ""}
        </div>
      </div>
      <div class="card-footer">
        <div><strong>${rate}</strong> <span>${rating}</span></div>
        <button class="expand-btn" type="button" aria-expanded="false" onclick="toggleCard(this)">Details</button>
      </div>
    </article>`;
}

window.toggleCard = function(button) {
  const card = button.closest(".result-card");
  if (!card) return;
  const expanded = card.classList.toggle("expanded");
  button.setAttribute("aria-expanded", expanded ? "true" : "false");
  button.textContent = expanded ? "Less" : "Details";
};

function formatNumber(value) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}
