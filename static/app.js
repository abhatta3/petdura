let allResults = [];
let catalogData = null;
let currentUser = null; // Stores logged-in user object { user_id, name, zip_code, account_type, ... }

const searchForm = document.getElementById("search-form");
const zipInput = document.getElementById("zip-input");
const zipInputGroup = document.getElementById("zip-input-group");
const loggedInZipBanner = document.getElementById("logged-in-zip-banner");
const loggedInLocationText = document.getElementById("logged-in-location-text");
const searchBtn = document.getElementById("search-btn");
const catalogSummary = document.getElementById("catalog-summary");
const controlsPanel = document.getElementById("controls-panel");
const serviceFilter = document.getElementById("service-filter");
const sourceFilter = document.getElementById("source-filter");
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

// Auth Navigation Elements
const navAuthSection = document.getElementById("nav-auth-section");
const navUserSection = document.getElementById("nav-user-section");
const navUserName = document.getElementById("nav-user-name");
const navUserRole = document.getElementById("nav-user-role");
const navUserAvatar = document.getElementById("nav-user-avatar");

// Auth Modal Elements
const authModal = document.getElementById("auth-modal");
const modalTitle = document.getElementById("modal-title");
const btnTabSignin = document.getElementById("btn-tab-signin");
const btnTabRegister = document.getElementById("btn-tab-register");
const btnTabForgot = document.getElementById("btn-tab-forgot");
const authFields = document.getElementById("auth-fields");
const authError = document.getElementById("auth-error");
const authSubmitBtn = document.getElementById("auth-submit-btn");

let authMode = "login"; // "login" | "register" | "forgot"
let activeAccountType = "user"; // "user" | "service"

searchForm.addEventListener("submit", runSearch);
serviceFilter.addEventListener("change", runSearch);
sourceFilter.addEventListener("change", runSearch);
sortBy.addEventListener("change", renderResults);
zipLimitSelect.addEventListener("change", renderZipTable);

tabSearch.addEventListener("click", () => switchTab("search"));
tabZips.addEventListener("click", () => switchTab("zips"));

loadCatalogSummary();
checkSavedSession();

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
    buildSourceFilter(data.sources || []);
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

function buildSourceFilter(sources) {
  const current = sourceFilter.value;
  const sorted = [...new Set(sources)].sort();
  sourceFilter.innerHTML = '<option value="">All sources</option>' + sorted.map(source =>
    `<option value="${escapeAttr(source)}">${escapeHtml(source)}</option>`
  ).join("");
  if (sorted.includes(current)) sourceFilter.value = current;
}

function renderZipTable() {
  if (!catalogData || !catalogData.zip_codes) return;
  let rows = [...catalogData.zip_codes];
  const limitVal = zipLimitSelect.value;
  const totalCount = rows.length;
  if (limitVal !== "all") {
    const limitNum = parseInt(limitVal, 10) || 100;
    rows = rows.slice(0, limitNum);
  }
  zipCountBadge.textContent = `Showing ${rows.length} of ${totalCount} ZIP + Provider rows`;
  zipTbody.innerHTML = rows.map(row => {
    const provider = row.provider || "Unknown";
    const count = row.count || 0;
    const zip = row.zip_code || "";
    return `<tr onclick="searchZipSource('${escapeAttr(zip)}', '${escapeAttr(provider)}')" style="cursor:pointer">
      <td><strong>${escapeHtml(zip)}</strong></td>
      <td>${escapeHtml(row.address || "")}</td>
      <td>${escapeHtml(provider)}</td>
      <td>${count}</td>
    </tr>`;
  }).join("");
}

window.searchZip = function(zipCode) {
  zipInput.value = zipCode;
  serviceFilter.value = "";
  sourceFilter.value = "";
  sortBy.value = "relevance";
  switchTab("search");
  runSearch();
};
window.searchZipSource = function(zipCode, sourceName) {
  zipInput.value = zipCode;
  serviceFilter.value = "";
  sourceFilter.value = sourceName;
  sortBy.value = "relevance";
  switchTab("search");
  runSearch();
};

/* Auth Modal Management */
function openAuthModal(mode = "login") {
  authMode = mode;
  authError.classList.add("hidden");
  authModal.classList.remove("hidden");
  setModalMode(mode);
}

function closeAuthModal() {
  authModal.classList.add("hidden");
}

function setModalMode(mode) {
  authMode = mode;
  authError.classList.add("hidden");
  btnTabSignin.classList.toggle("active", mode === "login");
  btnTabRegister.classList.toggle("active", mode === "register");
  btnTabForgot.classList.toggle("active", mode === "forgot");

  if (mode === "login") {
    modalTitle.textContent = "Sign In to PetDura";
    authSubmitBtn.textContent = "Sign In";
  } else if (mode === "register") {
    modalTitle.textContent = "Create PetDura Account";
    authSubmitBtn.textContent = "Register & Connect";
  } else {
    modalTitle.textContent = "Reset Password";
    authSubmitBtn.textContent = "Update Password";
  }
  renderAuthFields();
}

function toggleAccountType(type) {
  activeAccountType = type;
  renderAuthFields();
}

function renderAuthFields() {
  let html = "";
  if (authMode === "login") {
    html = `
      <div class="form-field-group">
        <label>User ID</label>
        <input type="text" id="auth-userid" required placeholder="e.g. alice123">
      </div>
      <div class="form-field-group">
        <label>Password</label>
        <input type="password" id="auth-password" required placeholder="••••••••">
      </div>
    `;
  } else if (authMode === "register") {
    html = `
      <div class="form-field-group">
        <label>Full Name</label>
        <input type="text" id="auth-name" required placeholder="Alice Smith">
      </div>
      <div class="form-field-group">
        <label>Full Address (Optional)</label>
        <input type="text" id="auth-address" placeholder="123 Main St, Los Angeles">
      </div>
      <div class="form-field-group">
        <label>ZIP Code (Recommended)</label>
        <input type="text" id="auth-zip" maxlength="5" pattern="[0-9]{5}" placeholder="90001">
      </div>
      <div class="form-field-group">
        <label>Contact (Email / Phone)</label>
        <input type="text" id="auth-contact" required placeholder="alice@example.com">
      </div>
      <div class="form-field-group">
        <label>User ID</label>
        <input type="text" id="auth-userid" required placeholder="alice123">
      </div>
      <div class="form-field-group">
        <label>Password</label>
        <input type="password" id="auth-password" required placeholder="••••••••">
      </div>
    `;
    if (activeAccountType === "service") {
      html += `
        <div class="form-field-group">
          <label>Service Type</label>
          <input type="text" id="auth-servicetype" value="Pet Boarding & Sitting">
        </div>
        <div class="form-field-group">
          <label>Short Description</label>
          <input type="text" id="auth-desc" value="Professional local pet care services">
        </div>
      `;
    }
  } else {
    // Forgot Password
    html = `
      <p style="margin:0 0 10px; font-size:0.82rem; color:var(--muted)">Enter your registered Name and Address to reset your password and update your profile.</p>
      <div class="form-field-group">
        <label>Full Name</label>
        <input type="text" id="auth-name" required placeholder="Alice Smith">
      </div>
      <div class="form-field-group">
        <label>Full Address</label>
        <input type="text" id="auth-address" required placeholder="123 Main St, Los Angeles">
      </div>
      <div class="form-field-group">
        <label>New Password</label>
        <input type="password" id="auth-password" required placeholder="New secure password">
      </div>
    `;
  }
  authFields.innerHTML = html;
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  authError.classList.add("hidden");

  try {
    if (authMode === "login") {
      const userId = document.getElementById("auth-userid").value.trim();
      const password = document.getElementById("auth-password").value.trim();

      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_type: activeAccountType, user_id: userId, password: password })
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || "Login failed");

      setSessionUser(data.user);
      closeAuthModal();
    } else if (authMode === "register") {
      const payload = {
        account_type: activeAccountType,
        name: document.getElementById("auth-name").value.trim(),
        address: document.getElementById("auth-address").value.trim(),
        zip_code: document.getElementById("auth-zip").value.trim(),
        contact: document.getElementById("auth-contact").value.trim(),
        user_id: document.getElementById("auth-userid").value.trim(),
        password: document.getElementById("auth-password").value.trim()
      };
      if (activeAccountType === "service") {
        payload.service_type = document.getElementById("auth-servicetype").value.trim();
        payload.description = document.getElementById("auth-desc").value.trim();
      }

      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || "Registration failed");

      // Auto login after successful register
      alert("Registration successful! Logging you in.");
      setSessionUser({ ...data.account, account_type: activeAccountType });
      closeAuthModal();
    } else {
      // Forgot Password
      const payload = {
        account_type: activeAccountType,
        name: document.getElementById("auth-name").value.trim(),
        address: document.getElementById("auth-address").value.trim(),
        new_password: document.getElementById("auth-password").value.trim()
      };

      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || "Password reset failed");

      alert("Password successfully updated! Please sign in with your new password.");
      setModalMode("login");
    }
  } catch (err) {
    authError.textContent = err.message;
    authError.classList.remove("hidden");
  }
}

function setSessionUser(user) {
  currentUser = user;
  localStorage.setItem("petdura_user", JSON.stringify(user));
  updateUIAfterAuth();
}

function checkSavedSession() {
  const saved = localStorage.getItem("petdura_user");
  if (saved) {
    try {
      currentUser = JSON.parse(saved);
      updateUIAfterAuth();
    } catch (e) {
      localStorage.removeItem("petdura_user");
    }
  }
}

function logoutUser() {
  currentUser = null;
  localStorage.removeItem("petdura_user");
  updateUIAfterAuth();
  runSearch();
}

function updateUIAfterAuth() {
  if (currentUser) {
    navAuthSection.classList.add("hidden");
    navUserSection.classList.remove("hidden");
    navUserName.textContent = currentUser.name || currentUser.user_id;
    navUserRole.textContent = currentUser.account_type === "service" ? "Service Provider" : "Pet Owner";
    navUserAvatar.textContent = (currentUser.name || "U")[0].toUpperCase();

    if (currentUser.zip_code) {
      zipInputGroup.classList.add("hidden");
      loggedInZipBanner.classList.remove("hidden");
      loggedInLocationText.textContent = `ZIP ${currentUser.zip_code} (${currentUser.name || currentUser.user_id})`;
      zipInput.value = currentUser.zip_code;
    } else {
      zipInputGroup.classList.remove("hidden");
      loggedInZipBanner.classList.add("hidden");
    }
    runSearch();
  } else {
    navAuthSection.classList.remove("hidden");
    navUserSection.classList.add("hidden");
    zipInputGroup.classList.remove("hidden");
    loggedInZipBanner.classList.add("hidden");
  }
}

async function runSearch(event) {
  if (event) event.preventDefault();
  
  // If user is logged in, force their zip code
  let zipCode = currentUser && currentUser.zip_code ? currentUser.zip_code : zipInput.value.trim();
  if (!zipCode && (!currentUser || !currentUser.zip_code)) {
    if (!searchForm.reportValidity()) return;
  }

  const serviceType = serviceFilter.value.trim();
  const source = sourceFilter.value.trim();

  searchBtn.disabled = true;
  statusMessage.textContent = currentUser && currentUser.account_type === "user"
    ? "Loading registered local services for your profile…"
    : "Searching the local catalog…";

  try {
    const payload = { zip_code: zipCode };
    if (serviceType) payload.service_type = serviceType;
    if (source) payload.source = source;

    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Search failed");

    allResults = data.results || [];
    const sourceLabel = source ? ` from ${source}` : "";
    const serviceLabel = serviceType ? `${serviceType} ` : "";
    resultsTitle.textContent = `${serviceLabel}in ${zipCode}${sourceLabel}`;
    controlsPanel.classList.remove("hidden");
    renderResults();
    statusMessage.textContent = allResults.length
      ? ""
      : `No listings matched ${zipCode}. Showing public network listings.`;
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
  if (sort === "provider") return (a.provider_name || "").localeCompare(b.provider_name || "");
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
    ? `<a class="contact-link" href="${escapeAttr(row.profile_url)}" target="_blank" rel="noopener noreferrer">Contact / Message</a>`
    : "";
  const rating = row.rating === null
    ? "Not rated"
    : `★ ${formatNumber(row.rating)} · ${row.review_count ?? 0} reviews`;
  const rate = row.price_usd === null
    ? "Rate unavailable"
    : `$${formatNumber(row.price_usd)} ${escapeHtml(row.price_unit || "per service")}`;

  return `
    <article class="result-card">
      <div class="card-top">
        <div class="result-topline">
          <span class="service-pill">${escapeHtml(row.service_type || "Pet Care")}</span>
          <span class="source">${escapeHtml(row.source || "Public Directory")}</span>
        </div>
        <div class="provider-row">
          <h3>${escapeHtml(row.provider_name || row.name || "Provider")}</h3>
          ${profileLink}
        </div>
        <p class="location">${escapeHtml(row.city || row.address || "")}, ${escapeHtml(row.state || "CA")} ${escapeHtml(row.zip_code || "")}</p>
      </div>
      <div class="card-body">
        <p class="result-description">${escapeHtml(row.description || "No description provided.")}</p>
        <div class="expanded-details">
          <p class="pet-types">Pets: ${escapeHtml(row.pet_types || "All pets welcomed")}</p>
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
