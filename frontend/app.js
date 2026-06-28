const API_BASE = "http://127.0.0.1:8000";

const state = {
  market: "KRW-BTC",
  overview: null,
  forecast: null,
  health: null,
};

const $ = (id) => document.getElementById(id);

const formatScore = (value) => (Number.isFinite(value) ? value.toFixed(2) : "--");

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  return `${(Number(value) * 100).toFixed(2)}%`;
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return body;
}

function setLoading(isLoading) {
  $("refreshBtn").disabled = isLoading;
  $("apiStatus").textContent = isLoading ? "API 불러오는 중" : "API 연결됨";
  $("apiStatus").className = `status-dot ${isLoading ? "" : "ok"}`;
}

function setError(error) {
  $("apiStatus").textContent = "API 확인 필요";
  $("apiStatus").className = "status-dot error";
  $("updatedAt").textContent = error.message;
  $("scoreDescription").innerHTML = `<span class="error-box">${escapeHtml(error.message)}</span>`;
}

function gradeTone(score) {
  if (score >= 80) return "alert";
  if (score >= 60) return "warn";
  if (score <= 20) return "alert";
  if (score <= 40) return "warn";
  return "neutral";
}

function renderCurrent() {
  const current = state.overview.current;
  const score = Number(current.score);
  $("scoreValue").textContent = formatScore(score);
  $("scoreNeedle").style.left = `${Math.max(0, Math.min(100, score))}%`;
  $("scoreNeedle").style.transform = "translateX(-2px)";
  $("currentGrade").textContent = current.grade;
  $("currentGrade").className = `pill ${gradeTone(score)}`;
  $("scoreDescription").textContent = current.description;

  const indicators = Object.entries(current.indicators || {}).slice(0, 8);
  $("indicatorBars").innerHTML = indicators
    .map(([name, value]) => {
      const width = Math.max(0, Math.min(100, Number(value)));
      return `
        <div class="indicator-row">
          <span>${escapeHtml(name)}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
          <span>${formatScore(Number(value))}</span>
        </div>
      `;
    })
    .join("");
}

function computeReadiness() {
  const score = Number(state.overview.current.score);
  const mirrorCount = state.overview.historical_mirror?.similar_periods?.length || 0;
  const forecastItems = state.forecast?.forecast || [];
  const longest = forecastItems[forecastItems.length - 1];
  const withinBand = longest?.trend_direction === "within_error_band";
  const confidence = longest?.confidence_level;

  let readiness = 72;
  if (score >= 80 || score <= 20) readiness -= 18;
  if (score >= 60 || score <= 40) readiness -= 7;
  if (mirrorCount < 3) readiness -= 10;
  if (!withinBand) readiness -= 12;
  if (confidence === "low") readiness -= 10;
  if (confidence === "high") readiness += 4;
  readiness = Math.max(28, Math.min(92, readiness));

  let label = "점검 양호";
  let tone = "neutral";
  let title = "정보와 감정이 비교적 분리되어 보입니다.";
  if (readiness < 50) {
    label = "점검 필요";
    tone = "alert";
    title = "판단보다 근거 확인이 먼저 필요한 상태입니다.";
  } else if (readiness < 68) {
    label = "추가 확인";
    tone = "warn";
    title = "불확실성이 남아 있어 한 번 더 확인할 구간입니다.";
  }

  const copy = withinBand
    ? "FOMO Score 참고값이 오차 범위 안에 있어 방향을 단정하지 않습니다."
    : "FOMO Score 참고값이 오차 범위를 벗어나도 가격이나 수익률 전망은 아닙니다.";

  return { readiness, label, tone, title, copy, withinBand, mirrorCount, confidence };
}

function renderReadiness() {
  const info = computeReadiness();
  $("readinessValue").textContent = `${Math.round(info.readiness)}`;
  $("readinessValue").style.borderColor =
    info.tone === "alert" ? "#f0b7b7" : info.tone === "warn" ? "#f3d394" : "#b8dad6";
  $("readinessLabel").textContent = info.label;
  $("readinessLabel").className = `pill ${info.tone}`;
  $("readinessTitle").textContent = info.title;
  $("readinessCopy").textContent = info.copy;

  const checks = [
    {
      title: "오차 먼저",
      copy: info.withinBand ? "흐름 참고값이 오차 범위 안입니다." : "오차 범위 밖 변화도 관찰값입니다.",
    },
    {
      title: "과거 사례",
      copy: `${info.mirrorCount}개 유사 구간을 함께 확인했습니다.`,
    },
    {
      title: "감정 분리",
      copy: "Decision Pause 질문으로 판단 근거를 다시 봅니다.",
    },
  ];

  $("checkGrid").innerHTML = checks
    .map(
      (item) => `
        <div class="check-item">
          <strong>${escapeHtml(item.title)}</strong>
          <p>${escapeHtml(item.copy)}</p>
        </div>
      `,
    )
    .join("");
}

function renderChart() {
  const items = state.overview.history.items || [];
  const svg = $("historyChart");
  const width = 900;
  const height = 260;
  const pad = 34;
  const usableW = width - pad * 2;
  const usableH = height - pad * 2;
  const points = items.map((item, index) => {
    const x = pad + (items.length <= 1 ? 0 : (index / (items.length - 1)) * usableW);
    const y = pad + (1 - Number(item.score) / 100) * usableH;
    return { x, y, score: Number(item.score), date: item.date };
  });

  if (!points.length) {
    svg.innerHTML = "";
    return;
  }

  const line = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = `${pad},${height - pad} ${line} ${width - pad},${height - pad}`;
  const grid = [20, 40, 60, 80]
    .map((value) => {
      const y = pad + (1 - value / 100) * usableH;
      return `<line class="chart-grid-line" x1="${pad}" y1="${y}" x2="${width - pad}" y2="${y}"></line>
        <text x="6" y="${y + 4}" fill="#687386" font-size="12">${value}</text>`;
    })
    .join("");
  const last = points[points.length - 1];

  svg.innerHTML = `
    ${grid}
    <polygon class="chart-area" points="${area}"></polygon>
    <polyline class="chart-line" points="${line}"></polyline>
    <circle class="chart-dot" cx="${last.x}" cy="${last.y}" r="5"></circle>
    <text x="${Math.max(pad, last.x - 96)}" y="${Math.max(18, last.y - 12)}" fill="#18202a" font-size="13" font-weight="800">
      ${formatScore(last.score)}
    </text>
  `;
  $("historyRange").textContent = `최근 ${items.length}개 관찰값`;
}

function renderMirror() {
  const periods = state.overview.historical_mirror?.similar_periods || [];
  $("mirrorList").innerHTML = periods.length
    ? periods
        .slice(0, 5)
        .map(
          (item) => `
          <div class="mirror-card">
            <div class="card-top">
              <div>
                <div class="card-title">${escapeHtml(item.date)}</div>
                <div class="card-meta">${escapeHtml(item.grade)} · 현재와 ${formatScore(Math.abs(Number(item.score_gap || 0)))}점 차이</div>
              </div>
              <span class="pill ${gradeTone(Number(item.score))}">${formatScore(Number(item.score))}</span>
            </div>
            <p class="card-copy">${escapeHtml(item.summary)}</p>
            <div class="metric-row">
              <div class="metric"><span>3D 참고</span><strong>${formatPercent(item.ret_3d)}</strong></div>
              <div class="metric"><span>7D 참고</span><strong>${formatPercent(item.ret_7d)}</strong></div>
              <div class="metric"><span>30D 참고</span><strong>${formatPercent(item.ret_30d)}</strong></div>
            </div>
          </div>
        `,
        )
        .join("")
    : '<div class="mirror-card">유사 구간 표본이 부족합니다.</div>';
}

function renderForecast() {
  const items = state.forecast?.forecast || [];
  $("forecastList").innerHTML = items
    .map((item, index) => {
      const featured = index === items.length - 1 ? " featured" : "";
      return `
        <div class="forecast-card${featured}">
          <div class="card-top">
            <div>
              <div class="card-title">${item.horizon_days}일 참고 흐름</div>
              <div class="card-meta">${escapeHtml(item.confidence_label)} · ${escapeHtml(item.trend_label)}</div>
            </div>
            <span class="pill ${item.trend_direction === "within_error_band" ? "neutral" : "warn"}">${escapeHtml(item.trend_label)}</span>
          </div>
          <p class="card-copy">${escapeHtml(item.interpretation)}</p>
          <div class="metric-row">
            <div class="metric"><span>참고값</span><strong>${formatScore(Number(item.predicted_score))}</strong></div>
            <div class="metric"><span>현재 대비</span><strong>${formatScore(Number(item.score_delta))}</strong></div>
            <div class="metric"><span>오차 범위</span><strong>${formatScore(Number(item.error_band))}</strong></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderPause() {
  const items = state.overview.decision_pause?.items || [];
  $("pauseList").innerHTML = items
    .map(
      (item) => `
      <div class="pause-card">
        <strong>${escapeHtml(item.category)}</strong>
        <p class="card-copy">${escapeHtml(item.question)}</p>
      </div>
    `,
    )
    .join("");
}

function renderAll() {
  renderCurrent();
  renderReadiness();
  renderChart();
  renderMirror();
  renderForecast();
  renderPause();
  $("disclaimerText").textContent =
    state.overview.disclaimer || state.health?.disclaimer || "시장 상태 관찰 도구입니다.";
  $("updatedAt").textContent = new Date().toLocaleString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

async function loadDashboard() {
  setLoading(true);
  try {
    const market = state.market;
    const [health, overview, forecast] = await Promise.all([
      fetchJson("/api/health"),
      fetchJson(
        `/api/mvp-overview?market=${encodeURIComponent(market)}&history_days=120&mirror_days=200&tolerance=10&max_periods=5`,
      ),
      fetchJson(`/api/score-forecast?market=${encodeURIComponent(market)}&days=200`),
    ]);
    state.health = health;
    state.overview = overview;
    state.forecast = forecast;
    setLoading(false);
    renderAll();
  } catch (error) {
    setError(error);
  } finally {
    $("refreshBtn").disabled = false;
  }
}

$("marketSelect").addEventListener("change", (event) => {
  state.market = event.target.value;
  loadDashboard();
});

$("refreshBtn").addEventListener("click", loadDashboard);

loadDashboard();
