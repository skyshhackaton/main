const DEFAULT_API_ORIGIN = "http://127.0.0.1:8000";
const MARKETS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"];
const PAUSE_CHECKS = [
  {
    id: "evidence",
    title: "근거",
    copy: "가격 움직임 말고 확인한 정보가 있습니다.",
  },
  {
    id: "timing",
    title: "시점",
    copy: "늦게 관심이 생긴 것인지 구분했습니다.",
  },
  {
    id: "boundary",
    title: "범위",
    copy: "감당 가능한 범위와 바꿀 조건을 말할 수 있습니다.",
  },
  {
    id: "cooldown",
    title: "시간",
    copy: "지금 바로 판단하지 않아도 되는 시간을 확보했습니다.",
  },
];

const state = {
  market: "KRW-BTC",
  overview: null,
  forecast: null,
  pattern: null,
  health: null,
  marketSnapshots: [],
  errors: {},
  pauseChecks: Object.fromEntries(PAUSE_CHECKS.map((item) => [item.id, false])),
};

const $ = (id) => document.getElementById(id);

function normalizeApiBase(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function resolveApiBase() {
  const params = new URLSearchParams(window.location.search);
  const configured = normalizeApiBase(params.get("api") || localStorage.getItem("fomoBreakApiBase"));
  if (configured) return configured;

  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    const staticServerPorts = new Set(["3000", "4173", "5173", "5500", "8080"]);
    if (!staticServerPorts.has(window.location.port)) return "";
    if (["localhost", "127.0.0.1", "::1"].includes(window.location.hostname)) {
      return `${window.location.protocol}//${window.location.hostname}:8000`;
    }
  }

  return DEFAULT_API_ORIGIN;
}

const API_BASE = resolveApiBase();
const API_LABEL = API_BASE || window.location.origin || DEFAULT_API_ORIGIN;

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
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`);
  } catch (error) {
    throw new Error(`API 연결 실패 (${API_LABEL})`);
  }
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
  $("updatedAt").textContent = `${error.message} · ${API_LABEL}`;
  $("scoreValue").textContent = "--";
  $("currentGrade").textContent = "-";
  $("currentGrade").className = "pill alert";
  $("scoreDescription").innerHTML = `
    <span class="error-box">
      ${escapeHtml(error.message)}
      <br />백엔드 서버를 실행한 뒤 새로고침하세요.
    </span>
  `;
  $("indicatorBars").innerHTML = "";
  $("marketRadar").innerHTML = `<div class="empty-state">API 연결 후 시장 레이더가 표시됩니다.</div>`;
  $("radarSummary").textContent = "연결 필요";
  $("radarSummary").className = "pill alert";
  $("readinessValue").textContent = "--";
  $("readinessLabel").textContent = "확인 필요";
  $("readinessLabel").className = "pill alert";
  $("readinessTitle").textContent = "API 연결을 먼저 확인합니다.";
  $("readinessCopy").textContent = "시장 상태와 과거 참고 사례를 불러오지 못했습니다.";
  $("readinessBreakdown").innerHTML = "";
  $("checkGrid").innerHTML = "";
  $("historyChart").innerHTML = "";
  $("historyRange").textContent = "데이터 없음";
  $("mirrorList").innerHTML = `<div class="mirror-card">API 연결 후 과거 유사 구간이 표시됩니다.</div>`;
  $("uncertaintyLens").innerHTML = `<div class="empty-state">API 연결 후 오차 범위가 표시됩니다.</div>`;
  $("forecastList").innerHTML = "";
  $("patternList").innerHTML = "";
  $("pauseChecklist").innerHTML = "";
  $("pauseList").innerHTML = "";
}

function gradeTone(score) {
  if (score >= 80) return "alert";
  if (score >= 60) return "warn";
  if (score <= 20) return "alert";
  if (score <= 40) return "warn";
  return "neutral";
}

function checkedPauseCount() {
  return Object.values(state.pauseChecks).filter(Boolean).length;
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

function renderMarketRadar() {
  const snapshots = state.marketSnapshots;
  if (!snapshots.length) {
    $("marketRadar").innerHTML = `<div class="empty-state">선택한 마켓 기준으로 관찰 중입니다.</div>`;
    $("radarSummary").textContent = state.errors.radar ? "일부 확인 필요" : "계산 중";
    $("radarSummary").className = `pill ${state.errors.radar ? "warn" : "neutral"}`;
    return;
  }

  const scores = snapshots.map((item) => Number(item.current.score));
  const spread = Math.max(...scores) - Math.min(...scores);
  const average = scores.reduce((sum, score) => sum + score, 0) / scores.length;
  let label = "분산 관찰";
  let tone = "warn";
  if (spread < 8) {
    label = "동조 관찰";
    tone = "neutral";
  } else if (spread > 18) {
    label = "마켓별 차이 큼";
    tone = "alert";
  }
  $("radarSummary").textContent = `${label} · 평균 ${formatScore(average)}`;
  $("radarSummary").className = `pill ${tone}`;

  $("marketRadar").innerHTML = snapshots
    .map((item) => {
      const score = Number(item.current.score);
      const isActive = item.market === state.market;
      return `
        <button class="market-card ${isActive ? "active" : ""}" type="button" data-market="${escapeHtml(item.market)}">
          <div class="market-card-top">
            <div>
              <div class="market-name">${escapeHtml(item.market)}</div>
              <div class="card-meta">${escapeHtml(item.current.grade)}</div>
            </div>
            <div class="market-score">${formatScore(score)}</div>
          </div>
          <div class="market-bar" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, score))}%"></span></div>
          <p class="market-note">${escapeHtml(item.current.description)}</p>
        </button>
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
  const pauseCount = checkedPauseCount();

  let readiness = 72;
  if (score >= 80 || score <= 20) readiness -= 18;
  if (score >= 60 || score <= 40) readiness -= 7;
  if (mirrorCount < 3) readiness -= 10;
  if (!withinBand) readiness -= 12;
  if (confidence === "low") readiness -= 10;
  if (confidence === "high") readiness += 4;
  readiness += pauseCount * 4;
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

  return { readiness, label, tone, title, copy, withinBand, mirrorCount, confidence, pauseCount };
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

  $("readinessBreakdown").innerHTML = [
    ["오차", info.withinBand ? "범위 안" : "범위 밖"],
    ["과거", `${info.mirrorCount}개`],
    ["신뢰", info.confidence === "low" ? "낮음" : info.confidence === "high" ? "높음" : "보통"],
    ["점검", `${info.pauseCount}/${PAUSE_CHECKS.length}`],
  ]
    .map(
      ([label, value]) => `
        <div class="breakdown-item">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `,
    )
    .join("");

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
  if (!items.length) {
    $("forecastList").innerHTML = `
      <div class="forecast-card">
        <p class="card-copy">FOMO Score 흐름 참고값을 불러오지 못했습니다. 현재 점수와 과거 유사 구간을 먼저 확인합니다.</p>
      </div>
    `;
    return;
  }

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

function renderUncertaintyLens() {
  const currentScore = Number(state.forecast?.current_score ?? state.overview.current.score);
  const items = state.forecast?.forecast || [];
  if (!items.length) {
    $("uncertaintyLens").innerHTML = `<div class="empty-state">오차 범위 참고값을 불러오지 못했습니다.</div>`;
    return;
  }

  $("uncertaintyLens").innerHTML = items
    .map((item) => {
      const predicted = Number(item.predicted_score);
      const error = Number(item.error_band || 0);
      const bandStart = Math.max(0, predicted - error);
      const bandEnd = Math.min(100, predicted + error);
      const bandWidth = Math.max(1, bandEnd - bandStart);
      return `
        <div class="band-row">
          <div class="band-head">
            <span>${item.horizon_days}일</span>
            <span>${escapeHtml(item.trend_label)} · 오차 ${formatScore(error)}</span>
          </div>
          <div class="band-track" aria-hidden="true">
            <span class="band-error" style="left:${bandStart}%; width:${bandWidth}%"></span>
            <span class="band-current" style="left:${Math.max(0, Math.min(100, currentScore))}%"></span>
            <span class="band-predicted" style="left:${Math.max(0, Math.min(100, predicted))}%"></span>
          </div>
          <p class="band-caption">현재 점수와 참고값의 차이를 백테스트 오차 범위와 함께 확인합니다.</p>
        </div>
      `;
    })
    .join("");
}

function renderPattern() {
  const pattern = state.pattern;
  if (!pattern?.band?.mean?.length) {
    $("patternList").innerHTML = `
      <div class="pattern-card">
        <p class="card-copy">KNN 패턴 참고 사례를 불러오지 못했습니다. 과거 유사 구간과 오차 범위를 함께 확인합니다.</p>
      </div>
    `;
    return;
  }

  const steps = pattern.band.steps || [];
  const mean = pattern.band.mean || [];
  const p10 = pattern.band.p10 || [];
  const p90 = pattern.band.p90 || [];
  const endIndex = mean.length - 1;
  const endMean = mean[endIndex];
  const endLow = p10[endIndex];
  const endHigh = p90[endIndex];

  $("patternList").innerHTML = `
    <div class="pattern-card featured">
      <div class="card-top">
        <div>
          <div class="card-title">${pattern.window}일 패턴 · ${pattern.horizon}일 참고 분포</div>
          <div class="card-meta">과거 ${pattern.k}개 유사 패턴 기준</div>
        </div>
        <span class="pill neutral">${escapeHtml(pattern.metric)}</span>
      </div>
      <p class="card-copy">${escapeHtml(pattern.summary)}</p>
      <div class="metric-row">
        <div class="metric"><span>평균</span><strong>${formatScore(Number(endMean))}</strong></div>
        <div class="metric"><span>낮은 범위</span><strong>${formatScore(Number(endLow))}</strong></div>
        <div class="metric"><span>높은 범위</span><strong>${formatScore(Number(endHigh))}</strong></div>
      </div>
      <div class="pattern-path" aria-label="KNN 패턴 평균 경로">
        ${steps
          .map((step, index) => {
            const value = Number(mean[index]);
            const left = steps.length <= 1 ? 0 : (index / (steps.length - 1)) * 100;
            const top = 100 - Math.max(0, Math.min(100, value));
            return `<span title="${step}일 ${formatScore(value)}" style="left:${left}%; top:${top}%"></span>`;
          })
          .join("")}
      </div>
    </div>
    ${(pattern.candidates || [])
      .slice(0, 3)
      .map(
        (item) => `
          <div class="pattern-card">
            <div class="card-top">
              <div>
                <div class="card-title">${escapeHtml(item.match_end_date)}</div>
                <div class="card-meta">거리 ${formatScore(Number(item.distance))} · 종료 등급 ${escapeHtml(item.anchored_end_grade)}</div>
              </div>
              <span class="pill ${gradeTone(Number(item.match_end_score))}">${formatScore(Number(item.match_end_score))}</span>
            </div>
          </div>
        `,
      )
      .join("")}
  `;
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

function renderPauseChecklist() {
  $("pauseChecklist").innerHTML = PAUSE_CHECKS.map(
    (item) => `
      <button class="pause-toggle" type="button" data-check-id="${escapeHtml(item.id)}" aria-pressed="${state.pauseChecks[item.id]}">
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(item.copy)}</span>
      </button>
    `,
  ).join("");
}

function renderAll() {
  renderMarketRadar();
  renderCurrent();
  renderReadiness();
  renderChart();
  renderMirror();
  renderUncertaintyLens();
  renderForecast();
  renderPattern();
  renderPauseChecklist();
  renderPause();
  $("disclaimerText").textContent =
    state.overview.disclaimer || state.health?.disclaimer || "시장 상태 관찰 도구입니다.";
  $("updatedAt").textContent = new Date().toLocaleString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

async function fetchOptional(path) {
  try {
    return { data: await fetchJson(path), error: null };
  } catch (error) {
    return { data: null, error };
  }
}

async function loadDashboard() {
  setLoading(true);
  state.errors = {};
  try {
    const market = state.market;
    const overview = await fetchJson(
      `/api/mvp-overview?market=${encodeURIComponent(market)}&history_days=120&mirror_days=200&tolerance=10&max_periods=5`,
    );

    const [healthResult, forecastResult, patternResult, radarResults] = await Promise.all([
      fetchOptional("/api/health"),
      fetchOptional(`/api/score-forecast?market=${encodeURIComponent(market)}&days=200`),
      fetchOptional(
        `/api/knn-pattern?market=${encodeURIComponent(market)}&window=10&horizon=30&k=10&metric=raw`,
      ),
      Promise.all(
        MARKETS.map((item) =>
          fetchOptional(
            `/api/mvp-overview?market=${encodeURIComponent(item)}&history_days=30&mirror_days=120&tolerance=10&max_periods=3`,
          ),
        ),
      ),
    ]);

    const marketSnapshots = radarResults.map((result) => result.data).filter(Boolean);
    if (!marketSnapshots.some((item) => item.market === market)) {
      marketSnapshots.unshift({ market, current: overview.current });
    }

    if (healthResult.error) state.errors.health = healthResult.error;
    if (forecastResult.error) state.errors.forecast = forecastResult.error;
    if (patternResult.error) state.errors.pattern = patternResult.error;
    if (radarResults.some((result) => result.error)) state.errors.radar = true;

    state.health = healthResult.data;
    state.overview = overview;
    state.forecast = forecastResult.data;
    state.pattern = patternResult.data;
    state.marketSnapshots = marketSnapshots;
    renderAll();
    const hasOptionalErrors = Object.keys(state.errors).length > 0;
    $("apiStatus").textContent = hasOptionalErrors ? "일부 API 확인" : "API 연결됨";
    $("apiStatus").className = `status-dot ${hasOptionalErrors ? "" : "ok"}`;
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

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-check-id]");
  if (button) {
    const id = button.getAttribute("data-check-id");
    state.pauseChecks[id] = !state.pauseChecks[id];
    renderReadiness();
    renderPauseChecklist();
    return;
  }

  const marketCard = event.target.closest("[data-market]");
  if (!marketCard) return;
  const market = marketCard.getAttribute("data-market");
  if (market === state.market) return;
  state.market = market;
  $("marketSelect").value = market;
  loadDashboard();
});

loadDashboard();
