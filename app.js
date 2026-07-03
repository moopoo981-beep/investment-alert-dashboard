let allResults = [];
let currentFilter = "all";

async function loadJSON(path) {
  const response = await fetch(path + "?t=" + Date.now());
  if (!response.ok) throw new Error("Cannot load " + path);
  return response.json();
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return value;
  return number.toLocaleString("th-TH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function safeText(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

function priceStatus(asset) {
  const current = Number(asset.current_price);
  const target = Number(asset.buy_target_price);

  if (!asset.current_price || !asset.buy_target_price) {
    return { label: "รอข้อมูลราคา", cls: "badge-neutral" };
  }

  if (current <= target) {
    return { label: "ถึงจุดน่าซื้อ", cls: "badge-buy" };
  }

  return { label: "รอดู", cls: "badge-watch" };
}

function impactBadge(level) {
  const clean = String(level || "Low").trim();
  const lower = clean.toLowerCase();

  if (lower === "high") return '<span class="badge badge-high">High</span>';
  if (lower === "medium") return '<span class="badge badge-medium">Medium</span>';
  return '<span class="badge badge-low">Low</span>';
}

function renderPortfolioTable(portfolio) {
  const tbody = document.getElementById("portfolioTable");

  tbody.innerHTML = portfolio.map(asset => {
    const status = priceStatus(asset);

    return `
      <tr>
        <td><strong>${safeText(asset.symbol || "-")}</strong></td>
        <td>${safeText(asset.name || "-")}</td>
        <td>${safeText(asset.type || "-")}</td>
        <td>${formatNumber(asset.average_cost)}</td>
        <td>${formatNumber(asset.buy_target_price)}</td>
        <td>${formatNumber(asset.current_price)}</td>
        <td><span class="badge ${status.cls}">${status.label}</span></td>
      </tr>
    `;
  }).join("");
}

function renderAssetCards(portfolio) {
  const container = document.getElementById("assetCards");

  container.innerHTML = portfolio.map(asset => {
    const status = priceStatus(asset);

    return `
      <article class="asset-card">
        <div class="asset-symbol">
          <strong>${safeText(asset.symbol || "-")}</strong>
          <span class="badge ${status.cls}">${status.label}</span>
        </div>
        <p>${safeText(asset.name || "-")}</p>
        <div class="asset-price">${formatNumber(asset.current_price)}</div>
        <p>Target: ${formatNumber(asset.buy_target_price)} | Cost: ${formatNumber(asset.average_cost)}</p>
      </article>
    `;
  }).join("");
}

function getFilteredResults() {
  const keyword = document.getElementById("newsSearch").value.trim().toLowerCase();

  return allResults.filter(item => {
    const filterMatch =
      currentFilter === "all" ||
      (currentFilter === "alert" && item.trigger_alert === true) ||
      String(item.impact_level || "").toLowerCase() === currentFilter.toLowerCase();

    const text = [
      item.news_title,
      item.source,
      item.impact_level,
      item.analysis_summary,
      item.action_recommendation,
      ...(item.affected_assets || [])
    ].join(" ").toLowerCase();

    const keywordMatch = !keyword || text.includes(keyword);

    return filterMatch && keywordMatch;
  });
}

function renderResults() {
  const container = document.getElementById("resultsList");
  const results = getFilteredResults();

  if (!results || results.length === 0) {
    container.innerHTML = '<div class="empty-state">ยังไม่มีข่าวตามเงื่อนไขนี้ ลองเปลี่ยนตัวกรองหรือคำค้นหา</div>';
    return;
  }

  container.innerHTML = results.map(item => {
    const affected = Array.isArray(item.affected_assets) ? item.affected_assets : [];
    const isAlert = item.trigger_alert === true;
    const readButton = item.url
      ? `<a class="read-btn" href="${safeText(item.url)}" target="_blank" rel="noopener">อ่านข่าวต้นทาง →</a>`
      : `<span class="read-btn disabled">ยังไม่มีลิงก์ข่าว</span>`;

    return `
      <article class="news-card ${isAlert ? "alert" : ""}">
        <div class="news-top">
          <div>
            <h3 class="news-title">${safeText(item.news_title || "-")}</h3>
            <div class="news-meta">
              <span>${safeText(item.source || "-")}</span>
              <span>•</span>
              <span>${safeText(item.time || "-")}</span>
              ${isAlert ? '<span>• 🚨 ต้องสนใจ</span>' : ''}
            </div>
          </div>
          ${impactBadge(item.impact_level)}
        </div>

        <p class="news-summary">${safeText(item.analysis_summary || "-")}</p>

        <div class="news-action">
          ${safeText(item.action_recommendation || "รอดูสถานการณ์")}
        </div>

        <div class="news-bottom">
          <div class="news-meta">
            Affected: ${affected.length ? affected.map(safeText).join(", ") : "-"}
          </div>
          ${readButton}
        </div>
      </article>
    `;
  }).join("");
}

function setupFilters() {
  document.querySelectorAll(".filter-btn").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach(btn => btn.classList.remove("active"));
      button.classList.add("active");
      currentFilter = button.dataset.filter;
      renderResults();
    });
  });

  document.getElementById("newsSearch").addEventListener("input", renderResults);
}

function setupTheme() {
  const button = document.getElementById("themeToggle");
  const saved = localStorage.getItem("theme");

  if (saved === "dark") {
    document.body.classList.add("dark");
    button.textContent = "☀️";
  }

  button.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    const isDark = document.body.classList.contains("dark");
    localStorage.setItem("theme", isDark ? "dark" : "light");
    button.textContent = isDark ? "☀️" : "🌙";
  });
}

function updateFocus(results, portfolio) {
  const alerts = results.filter(item => item.trigger_alert === true);
  const high = results.filter(item => String(item.impact_level || "").toLowerCase() === "high");

  if (alerts.length > 0) {
    document.getElementById("todayFocus").textContent = `มี ${alerts.length} ข่าวที่ควรเช็ก`;
    document.getElementById("todayFocusSub").textContent = "เปิดดูรายการ Alert ก่อน แล้วค่อยตัดสินใจซื้อเพิ่มหรือรอดู";
    return;
  }

  if (high.length > 0) {
    document.getElementById("todayFocus").textContent = "มีข่าวระดับ High";
    document.getElementById("todayFocusSub").textContent = "ควรอ่านรายละเอียดข่าวและผลกระทบต่อหุ้นในพอร์ต";
    return;
  }

  document.getElementById("todayFocus").textContent = "ยังไม่มีสัญญาณเร่งด่วน";
  document.getElementById("todayFocusSub").textContent = "อ่านข่าวล่าสุดและอัปเดตราคาเป้าหมายได้ตามปกติ";
}

async function init() {
  setupTheme();
  setupFilters();

  try {
    const portfolio = await loadJSON("data/portfolio.json");
    allResults = await loadJSON("data/results.json");

    renderPortfolioTable(portfolio);
    renderAssetCards(portfolio);
    renderResults();

    const alertCount = allResults.filter(item => item.trigger_alert === true).length;
    const targetCount = portfolio.filter(asset => {
      const current = Number(asset.current_price);
      const target = Number(asset.buy_target_price);
      return asset.current_price && asset.buy_target_price && current <= target;
    }).length;

    document.getElementById("assetCount").textContent = portfolio.length;
    document.getElementById("newsCount").textContent = allResults.length;
    document.getElementById("alertCount").textContent = alertCount;
    document.getElementById("targetCount").textContent = targetCount;
    document.getElementById("lastUpdated").textContent =
      "Updated " + new Date().toLocaleString("th-TH");

    updateFocus(allResults, portfolio);

  } catch (error) {
    console.error(error);
    document.getElementById("resultsList").innerHTML =
      '<div class="empty-state">โหลดข้อมูลไม่สำเร็จ กรุณาตรวจสอบไฟล์ data/portfolio.json และ data/results.json</div>';
    document.getElementById("todayFocus").textContent = "โหลดข้อมูลไม่สำเร็จ";
    document.getElementById("todayFocusSub").textContent = "ตรวจสอบว่าไฟล์ JSON อยู่ถูกตำแหน่งใน GitHub";
  }
}

init();
