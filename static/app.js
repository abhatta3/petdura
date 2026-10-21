let allResults = [];
let catalogData = null;

const searchForm = document.getElementById("search-form");
const zipInput = document.getElementById("zip-input");
const descriptionInput = document.getElementById("description-input");
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
serviceFilter.addEventListener("change", renderFilteredResults);
maxPriceFilter.addEventListener("input", renderFilteredResults);
sortBy.addEventListener("change", renderFilteredResults);
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
    catalogSummary.textContent = `${data.listing_count} service listings across ${data.zip_count} ZIP codes in this catalog.`;
    renderZipTable();
  } catch (error) {
    catalogSummary.textContent = error.message;
  }
}

function renderZipTable() {
  if (!catalogData || !catalogData.zip_codes) return;
  let zips = [...catalogData.zip_codes];
  
  // Sort by zip code ascending
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
  descriptionInput.value = "";
  switchTab("search");
  searchForm.dispatchEvent(new Event("submit"));
};

async function runSearch(event) {
  event.preventDefault();
  if (!searchForm.reportValidity()) return;

  const zipCode = zipInput.value.trim();
  const description = descriptionInput.value.trim();
  searchBtn.disabled = true;
  statusMessage.textContent = "Searching the local catalog…";

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ zip_code: zipCode, description }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Search failed");

    allResults = data.results || [];
    buildServiceFilter(allResults);
    resultsTitle.textContent = description
      ? `Matches in ${zipCode}`
      : `All services in ${zipCode}`;
    controlsPanel.classList.remove("hidden");
    renderFilteredResults();
    statusMessage.textContent = allResults.length
      ? ""
      : `No catalog entries matched ${zipCode}${description ? " and that description" : ""}.`;
  } catch (error) {
    allResults = [];
    controlsPanel.classList.add("hidden");
    resultsPanel.innerHTML = "";
    statusMessage.textContent = error.message;
  } finally {
    searchBtn.disabled = false;
  }
}

function buildServiceFilter(results) {
  const current = serviceFilter.value;
  const services = [...new Set(results.map(row => row.service_type))].sort();
  serviceFilter.innerHTML = `<option value="">All services</option>${services.map(service =>
    `<option value="${escapeAttr(service)}">${escapeHtml(service)}</option>`
  ).join("")}`;
  if (services.includes(current)) serviceFilter.value = current;
}

function renderFilteredResults() {
  const selectedService = serviceFilter.value;
  const maximumRate = maxPriceFilter.value === "" ? null : Number(maxPriceFilter.value);
  const selectedSort = sortBy.value;

  const filtered = allResults.filter(row =>
    (!selectedService || row.service_type === selectedService) &&
    (maximumRate === null || row.price_usd === null || row.price_usd <= maximumRate)
  );

  filtered.sort((a, b) => compareRows(a, b, selectedSort));
  resultsCount.textContent = `${filtered.length} of ${allResults.length}`;
  resultsPanel.innerHTML = filtered.map(renderCard).join("");
}

function compareRows(a, b, sort) {
  if (sort === "rating") return numberDescending(a.rating, b.rating);
  if (sort === "reviews") return numberDescending(a.review_count, b.review_count);
  if (sort === "price") return numberAscending(a.price_usd, b.price_usd);
  if (sort === "provider") return a.provider_name.localeCompare(b.provider_name);
  return numberDescending(a.relevance, b.relevance) ||
    numberDescending(a.rating, b.rating) ||
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
    ? `<a href="${escapeAttr(row.profile_url)}" target="_blank" rel="noopener noreferrer">View source</a>`
    : "";
  const rating = row.rating === null
    ? "Not rated"
    : `★ ${formatNumber(row.rating)} · ${row.review_count ?? 0} reviews`;
  const rate = row.price_usd === null
    ? "Rate unavailable"
    : `$${formatNumber(row.price_usd)} ${escapeHtml(row.price_unit)}`;

  return `
    <article class="result-card">
      <div class="result-topline">
        <span class="service-pill">${escapeHtml(row.service_type)}</span>
        <span class="source">${escapeHtml(row.source)}</span>
      </div>
      <h3>${escapeHtml(row.provider_name)}</h3>
      <p class="location">${escapeHtml(row.city)}, ${escapeHtml(row.state)} ${escapeHtml(row.zip_code)}</p>
      <p>${escapeHtml(row.description)}</p>
      <p class="pet-types">Pets: ${escapeHtml(row.pet_types)}</p>
      <div class="result-footer">
        <div><strong>${rate}</strong><span>${rating}</span></div>
        ${profileLink}
      </div>
    </article>`;
}

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
