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

const INTENT_MODES = {
  observe: {
    badge: "관찰 모드",
    title: "판단 전에 관찰값을 먼저 정리합니다.",
    copy: "시장 점수, 과거 유사 구간, 오차 범위, 현재가 표시값을 한 번에 확인합니다.",
    terminalLabel: "ORDER ROUTE",
    terminalAction: "CLOSED",
    terminalCopy: "공개 데이터 관찰값만 화면에 표시합니다.",
    tone: "neutral",
  },
  buy: {
    badge: "가상 매수 시도 차단",
    title: "가상 매수 시도를 주문 전송 전에 멈췄습니다.",
    copy: "이 장면은 실제 주문이 아니라, 판단 전 점검으로 넘어가기 전의 시도 화면입니다.",
    terminalLabel: "BUY INTENT",
    terminalAction: "ORDER PAUSED",
    terminalCopy: "주문 전송 없이 근거 확인 화면으로 흐름을 바꿉니다.",
    tone: "warn",
  },
  sell: {
    badge: "가상 매도 시도 차단",
    title: "가상 매도 시도를 주문 전송 전에 멈췄습니다.",
    copy: "불안이나 급한 반응을 실제 주문으로 연결하지 않고, 근거 점검으로 넘기기 전 화면을 보여줍니다.",
    terminalLabel: "SELL INTENT",
    terminalAction: "ORDER PAUSED",
    terminalCopy: "급한 반응을 자기 점검 질문으로 바꾸기 전에 멈춥니다.",
    tone: "alert",
  },
};

const DEMO_TOTAL_MS = 90000;
const DEMO_FLOW = [
  ["시도 인식", "사용자가 가상 행동 버튼을 누릅니다."],
  ["실거래 차단", "주문 전송과 API Key 입력은 없습니다."],
  ["근거 분리", "점수·오차·과거 사례를 함께 봅니다."],
  ["일시정지", "Decision Pause 질문으로 마무리합니다."],
];
const DEMO_SCRIPT = [
  {
    delay: 0,
    mode: "observe",
    step: 0,
    title: "1. 시장 상태를 먼저 엽니다",
    copy: "API 연결, 선택 마켓, 표시용 현재가와 FOMO Score를 같은 화면에서 확인합니다.",
  },
  {
    delay: 12000,
    mode: "buy",
    step: 0,
    title: "2. 가상 매수 시도가 들어옵니다",
    copy: "사용자가 가격 움직임에 반응하려는 순간을 시연합니다. 실제 주문 기능은 열리지 않습니다.",
  },
  {
    delay: 28000,
    mode: "buy",
    step: 1,
    title: "3. 주문 경로를 차단합니다",
    copy: "API Key 입력과 주문 전송 없이, 공개 데이터 기반 관찰 화면으로 흐름을 돌립니다.",
  },
  {
    delay: 43000,
    mode: "buy",
    step: 2,
    title: "4. 판단 근거를 나눕니다",
    copy: "현재 점수, 과거 참고 구간, 오차 범위, 표시용 현재가를 함께 보여줍니다.",
  },
  {
    delay: 58000,
    mode: "buy",
    step: 3,
    title: "5. Decision Pause로 멈춥니다",
    copy: "지금 판단의 근거가 정보인지 감정인지 체크리스트로 확인합니다.",
  },
  {
    delay: 72000,
    mode: "sell",
    step: 0,
    title: "6. 가상 매도 시도도 같은 원칙입니다",
    copy: "불안한 반응도 주문으로 연결하지 않고 근거 점검으로 전환합니다.",
  },
  {
    delay: 84000,
    mode: "sell",
    step: 3,
    title: "7. 안전한 MVP 원칙으로 마무리합니다",
    copy: "투자 추천 없이 시장 상태 관찰, 과거 참고 사례, 자기 점검만 제공합니다.",
  },
];

const state = {
  market: "KRW-BTC",
  overview: null,
  forecast: null,
  pattern: null,
  ticker: null,
  health: null,
  marketSnapshots: [],
  errors: {},
  intentMode: "observe",
  demoStep: 0,
  demoStartedAt: null,
  demoScriptIndex: 0,
  demoTimers: [],
  virtualQuantity: "0.05",
  virtualOrderLog: null,
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

const formatDemoTime = (value) => {
  const totalSeconds = Math.max(0, Math.floor(Number(value) / 1000));
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
};

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  return `${(Number(value) * 100).toFixed(2)}%`;
};

const formatKrw = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  return Number(value).toLocaleString("ko-KR");
};

const formatSignedPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  const numeric = Number(value) * 100;
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(2)}%`;
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
  renderDemoStage();
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

function tickerForMarket(market) {
  return (state.ticker?.items || []).find((item) => item.market === market);
}

function updateDemoProgress(elapsedMs = 0) {
  const clock = $("demoClock");
  const progress = $("demoProgress");
  if (!clock || !progress) return;
  const elapsed = Math.max(0, Math.min(DEMO_TOTAL_MS, elapsedMs));
  clock.textContent = `${formatDemoTime(elapsed)} / ${formatDemoTime(DEMO_TOTAL_MS)}`;
  progress.style.width = `${(elapsed / DEMO_TOTAL_MS) * 100}%`;
}

function clearDemoTimers() {
  state.demoTimers.forEach((timer) => {
    window.clearTimeout(timer);
    window.clearInterval(timer);
  });
  state.demoTimers = [];
  state.demoStartedAt = null;
  const button = $("demoAutoBtn");
  if (button) button.textContent = "90초 가이드 시작";
  updateDemoProgress(0);
}

function setIntentMode(mode, step = 0) {
  state.intentMode = mode;
  state.demoStep = step;
  renderDemoStage();
}

function focusDecisionPausePreview() {
  window.requestAnimationFrame(() => {
    const preview = document.querySelector(".pause-preview");
    const firstCheck = $("quickPauseList")?.querySelector("button");
    preview?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    firstCheck?.focus({ preventScroll: true });
  });
}

function activateDecisionPause() {
  clearDemoTimers();
  state.demoStep = 3;
  state.demoScriptIndex = 4;
  renderDemoStage();
  if (state.overview) {
    renderReadiness();
    renderPauseChecklist();
  }
  focusDecisionPausePreview();
}

function renderDemoStage() {
  const mode = INTENT_MODES[state.intentMode] || INTENT_MODES.observe;
  const current = state.overview?.current;
  const score = Number(current?.score);
  const grade = current?.grade || "데이터 대기";
  const mirrorCount = state.overview?.historical_mirror?.similar_periods?.length || 0;
  const topMirror = state.overview?.historical_mirror?.similar_periods?.[0];
  const forecastItems = state.forecast?.forecast || [];
  const longest = forecastItems[forecastItems.length - 1];
  const ticker = tickerForMarket(state.market);
  const pauseCount = checkedPauseCount();
  const ticketMode = state.intentMode === "sell" ? "sell" : state.intentMode === "buy" ? "buy" : "observe";
  const isBuy = ticketMode === "buy";
  const isSell = ticketMode === "sell";
  const isAttempt = isBuy || isSell;
  const selectedAction = isBuy ? "BUY INTENT" : isSell ? "SELL INTENT" : "INTENT READY";
  const selectedLabel = isBuy ? "가상 매수 시도" : isSell ? "가상 매도 시도" : "가상 행동 대기";
  const readinessInfo = state.overview?.current ? computeReadiness() : null;
  const readinessValue = readinessInfo ? Math.round(readinessInfo.readiness) : "--";
  const readinessTone = readinessInfo?.tone || "neutral";
  const observationFlow = [
    ["1", "공개 데이터", ticker ? "현재가 표시" : "연결 확인"],
    ["2", "과거 사례", topMirror ? topMirror.date : `${mirrorCount}개 표본`],
    ["3", "오차 범위", longest ? `±${formatScore(Number(longest.error_band))}` : "계산 중"],
    ["4", "자기 점검", `${pauseCount}/${PAUSE_CHECKS.length}개 확인`],
  ];
  const selectedCopy = isAttempt
    ? "아래 장면은 사용자가 행동 버튼을 누른 직후입니다. 가상 수량 입력과 전송 시도는 화면 안에서만 처리됩니다."
    : "가상 매수 또는 가상 매도 버튼을 누르면, 이 영역이 실제 사용 장면처럼 바뀝니다.";
  const virtualQuantity = state.virtualQuantity || "";
  const virtualLog = state.virtualOrderLog;

  $("firewallBadge").textContent = mode.badge;
  $("firewallBadge").className = mode.tone;
  $("intentTitle").textContent = mode.title;
  $("intentCopy").textContent = mode.copy;
  $("orderTerminal").className = `order-terminal ${mode.tone}`;
  $("terminalLabel").textContent = mode.terminalLabel;
  $("terminalAction").textContent = mode.terminalAction;
  $("terminalCopy").textContent = mode.terminalCopy;
  document
    .querySelector(".pause-preview")
    ?.classList.toggle("active", state.demoStep >= 3);

  document.querySelectorAll("[data-intent-mode]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-intent-mode") === state.intentMode);
  });

  const activeScript = DEMO_SCRIPT[state.demoScriptIndex] || DEMO_SCRIPT[0];
  $("demoCaption").textContent = state.demoStartedAt ? activeScript.title : "발표 속도에 맞춰 천천히 전환됩니다.";
  $("demoScript").innerHTML = `
    <span>Presentation cue</span>
    <strong>${escapeHtml(activeScript.title)}</strong>
    <p>${escapeHtml(activeScript.copy)}</p>
  `;
  updateDemoProgress(state.demoStartedAt ? Date.now() - state.demoStartedAt : 0);

  $("attemptScene").className = `attempt-scene ${mode.tone}`;
  $("attemptScene").innerHTML = `
    <div class="attempt-head">
      <div>
        <span>STEP 1 · VIRTUAL INTENT SCREEN</span>
        <strong>Decision Pause 전 가상 매수·매도 시도 장면</strong>
      </div>
      <em>${escapeHtml(selectedAction)}</em>
    </div>
    <p class="attempt-copy">${escapeHtml(selectedCopy)}</p>
    <div class="firewall-map" aria-label="가상 주문 처리 상태">
      <div class="map-node trigger ${isAttempt ? "active" : ""}">
        <span>입력</span>
        <strong>${isAttempt ? escapeHtml(selectedLabel) : "가상 행동 선택"}</strong>
      </div>
      <div class="map-node gate active">
        <span>차단</span>
        <strong>주문 API 호출 없음</strong>
      </div>
      <div class="map-node pause ${state.demoStep >= 3 ? "active" : ""}">
        <span>확인</span>
        <strong>Decision Pause</strong>
      </div>
    </div>
    <div class="attempt-body">
      <button class="attempt-card buy ${isBuy ? "active" : ""}" type="button" data-intent-mode="buy">
        <span>가상 매수 화면</span>
        <strong>${isBuy ? "시도 감지" : "대기"}</strong>
        <small>가상 수량 입력 · 실제 주문 없음</small>
      </button>
      <button class="attempt-card sell ${isSell ? "active" : ""}" type="button" data-intent-mode="sell">
        <span>가상 매도 화면</span>
        <strong>${isSell ? "시도 감지" : "대기"}</strong>
        <small>전송 시도 차단 · API Key 없음</small>
      </button>
      <div class="attempt-terminal ${mode.tone}">
        <span>${escapeHtml(selectedLabel)}</span>
        <strong>${isAttempt ? "주문 전송 전 차단" : "선택 전 관찰"}</strong>
        <dl>
          <div><dt>마켓</dt><dd>${escapeHtml(state.market)}</dd></div>
          <div><dt>표시용 현재가</dt><dd>${ticker ? `${formatKrw(ticker.trade_price)} KRW` : "확인 중"}</dd></div>
          <div><dt>FOMO Score</dt><dd>${Number.isFinite(score) ? formatScore(score) : "--"}</dd></div>
        </dl>
      </div>
    </div>
    <form class="virtual-order-form" aria-label="화면 시연용 가상 주문 입력">
      <label>
        <span>가상 수량</span>
        <input
          id="virtualQuantityInput"
          type="number"
          min="0"
          step="0.0001"
          inputmode="decimal"
          value="${escapeHtml(virtualQuantity)}"
          placeholder="0.05"
          ${isAttempt ? "" : "disabled"}
        />
      </label>
      <button class="virtual-submit ${mode.tone}" type="button" data-virtual-submit ${isAttempt ? "" : "disabled"}>
        가상 주문 전송 시도
      </button>
      <p>${isAttempt ? "입력값은 저장되지 않고, 클릭 즉시 Decision Pause 전 차단 로그로만 남습니다." : "먼저 가상 매수 또는 가상 매도 화면을 선택합니다."}</p>
    </form>
    <div class="virtual-order-log ${virtualLog ? mode.tone : "neutral"}" aria-live="polite">
      <span>${virtualLog ? "차단 로그" : "대기 로그"}</span>
      <strong>${virtualLog ? escapeHtml(virtualLog.title) : "가상 주문 전송 시도 전"}</strong>
      <p>${virtualLog ? escapeHtml(virtualLog.copy) : "수량 입력과 전송 버튼은 실제 거래가 아니라 Decision Pause 시연을 위한 화면 요소입니다."}</p>
    </div>
    <div class="attempt-route" aria-label="가상 시도 이후 흐름">
      <div class="${isAttempt && state.demoStep >= 0 ? "active" : ""}"><span>1</span><strong>가상 시도</strong></div>
      <div class="${isAttempt && state.demoStep >= 1 ? "active" : ""}"><span>2</span><strong>주문 차단</strong></div>
      <div class="${isAttempt && state.demoStep >= 2 ? "active" : ""}"><span>3</span><strong>관찰값 확인</strong></div>
      <div class="${isAttempt && state.demoStep >= 3 ? "active" : ""}"><span>4</span><strong>Decision Pause</strong></div>
    </div>
  `;

  $("observationConsole").innerHTML = `
    <div class="observation-head">
      <div>
        <span>PUBLIC DATA OBSERVATION</span>
        <strong>${escapeHtml(state.market)}</strong>
      </div>
      <em>실시간 주문 화면이 아닌 관찰 화면</em>
    </div>
    <div class="observation-main">
      <div class="observation-score">
        <span>FOMO Score</span>
        <strong>${Number.isFinite(score) ? formatScore(score) : "--"}</strong>
        <p>${escapeHtml(grade)}</p>
      </div>
      <div class="observation-price">
        <span>표시용 현재가</span>
        <strong>${ticker ? `${formatKrw(ticker.trade_price)} KRW` : "불러오는 중"}</strong>
        <p>${ticker ? formatSignedPercent(ticker.signed_change_rate) : "Upbit 공개 ticker"}</p>
      </div>
    </div>
    <div class="observation-grid">
      <div>
        <span>과거 참고 사례</span>
        <strong>${topMirror ? escapeHtml(topMirror.date) : "표본 확인 중"}</strong>
        <p>${topMirror ? `${formatScore(Number(topMirror.score))} · ${escapeHtml(topMirror.grade)}` : `${mirrorCount}개 유사 구간`}</p>
      </div>
      <div>
        <span>오차 범위</span>
        <strong>${longest ? `±${formatScore(Number(longest.error_band))}` : "확인 중"}</strong>
        <p>${longest ? escapeHtml(longest.trend_label) : "방향 단정 없음"}</p>
      </div>
      <div>
        <span>자기 점검</span>
        <strong>${pauseCount}/${PAUSE_CHECKS.length}</strong>
        <p>정보와 감정 분리</p>
      </div>
    </div>
    <div class="observation-flow" aria-label="공개 데이터 관찰 흐름">
      ${observationFlow
        .map(
          ([index, label, value]) => `
            <div>
              <span>${escapeHtml(index)}</span>
              <strong>${escapeHtml(label)}</strong>
              <p>${escapeHtml(value)}</p>
            </div>
          `,
        )
        .join("")}
    </div>
  `;

  const ticketLabel = ticketMode === "sell" ? "가상 매도 티켓" : ticketMode === "buy" ? "가상 매수 티켓" : "가상 행동 대기";
  const ticketAction = ticketMode === "sell" ? "SELL INTENT" : ticketMode === "buy" ? "BUY INTENT" : "OBSERVE";
  const ticketCopy =
    ticketMode === "observe"
      ? "가상 행동을 선택하거나 전환 버튼을 누르면 실제 주문 대신 점검 화면이 열립니다."
      : "이 화면은 주문 입력 화면처럼 보이지만 실제 주문 전송과 API Key 입력은 없습니다. 수량은 시연용 입력값입니다.";
  $("intentTicket").className = `intent-ticket ${mode.tone}`;
  $("intentTicket").innerHTML = `
    <div class="ticket-head">
      <div>
        <span>Virtual Trade Intent</span>
        <strong>${ticketLabel}</strong>
      </div>
      <em>${ticketAction}</em>
    </div>
    <div class="ticket-tabs">
      <button class="ticket-tab" type="button" data-intent-mode="buy">가상 매수</button>
      <button class="ticket-tab" type="button" data-intent-mode="sell">가상 매도</button>
    </div>
    <div class="ticket-fields">
      <div><span>마켓</span><strong>${escapeHtml(state.market)}</strong></div>
      <div><span>표시용 현재가</span><strong>${ticker ? `${formatKrw(ticker.trade_price)} KRW` : "확인 중"}</strong></div>
      <div><span>FOMO Score</span><strong>${Number.isFinite(score) ? formatScore(score) : "--"}</strong></div>
      <div><span>API Key</span><strong>요구하지 않음</strong></div>
    </div>
    <p>${escapeHtml(ticketCopy)}</p>
    <button class="blocked-submit ${isAttempt ? mode.tone : "neutral"}" type="button" data-open-pause>
      ${isAttempt ? "주문 전송 없이 Decision Pause 열기" : "Decision Pause 바로 열기"}
    </button>
  `;
  $("intentTicket").querySelectorAll("[data-intent-mode]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-intent-mode") === ticketMode);
  });

  document.querySelector(".pause-live-status")?.remove();
  $("quickPauseList").insertAdjacentHTML(
    "beforebegin",
    `
      <div class="pause-live-status ${readinessTone}">
        <div>
          <span>판단 준비도</span>
          <strong>${escapeHtml(String(readinessValue))}</strong>
        </div>
        <p>Decision Pause 확인 ${pauseCount}/${PAUSE_CHECKS.length}개 · 체크하면 준비도에 바로 반영됩니다.</p>
        <div class="pause-progress" aria-hidden="true">
          <span style="width:${(pauseCount / PAUSE_CHECKS.length) * 100}%"></span>
        </div>
      </div>
    `,
  );
  $("quickPauseList").innerHTML = PAUSE_CHECKS.map(
    (item) => `
      <button class="quick-pause-toggle" type="button" data-check-id="${escapeHtml(item.id)}" aria-pressed="${state.pauseChecks[item.id]}">
        <span>${escapeHtml(item.title)}</span>
        <p>${escapeHtml(item.copy)}</p>
        <strong>${state.pauseChecks[item.id] ? "확인됨" : "확인 필요"}</strong>
      </button>
    `,
  ).join("");

  $("demoFlow").innerHTML = DEMO_FLOW.map(
    ([title, copy], index) => `
      <div class="flow-step ${index <= state.demoStep ? "active" : ""}">
        <span>${index + 1}</span>
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(copy)}</p>
      </div>
    `,
  ).join("");

  $("intentEvidence").innerHTML = [
    ["FOMO Score", Number.isFinite(score) ? `${formatScore(score)} · ${grade}` : grade],
    ["과거 참고", mirrorCount ? `${mirrorCount}개 유사 구간` : "표본 확인 중"],
    [
      "오차 범위",
      longest
        ? `${longest.trend_label} · ±${formatScore(Number(longest.error_band))}`
        : "참고값 확인 중",
    ],
    [
      "표시용 현재가",
      ticker ? `${formatKrw(ticker.trade_price)} KRW · ${formatSignedPercent(ticker.signed_change_rate)}` : "불러오는 중",
    ],
    ["자기 점검", `${pauseCount}/${PAUSE_CHECKS.length}개 확인`],
  ]
    .map(
      ([label, value]) => `
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `,
    )
    .join("");
}

function runDemoSequence() {
  clearDemoTimers();
  const button = $("demoAutoBtn");
  button.textContent = "90초 가이드 진행 중";
  state.demoStartedAt = Date.now();
  state.demoScriptIndex = 0;
  updateDemoProgress(0);

  state.demoTimers = DEMO_SCRIPT.map((item, index) =>
    window.setTimeout(() => {
      state.demoScriptIndex = index;
      setIntentMode(item.mode, item.step);
    }, item.delay),
  );

  const progressTimer = window.setInterval(() => {
    if (!state.demoStartedAt) return;
    updateDemoProgress(Date.now() - state.demoStartedAt);
  }, 500);
  state.demoTimers.push(progressTimer);

  state.demoTimers.push(window.setTimeout(() => {
    state.demoStartedAt = null;
    button.textContent = "90초 가이드 다시 시작";
    updateDemoProgress(DEMO_TOTAL_MS);
  }, DEMO_TOTAL_MS));
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
  const tickers = new Map((state.ticker?.items || []).map((item) => [item.market, item]));
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
      const ticker = tickers.get(item.market);
      const tickerTone = Number(ticker?.signed_change_rate || 0) > 0 ? "up" : "down";
      return `
        <button class="market-card ${isActive ? "active" : ""}" type="button" data-market="${escapeHtml(item.market)}">
          <div class="market-card-top">
            <div>
              <div class="market-name">${escapeHtml(item.market)}</div>
              <div class="card-meta">${escapeHtml(item.current.grade)}</div>
            </div>
            <div class="market-score">${formatScore(score)}</div>
          </div>
          ${
            ticker
              ? `<div class="ticker-line">
                  <span>${formatKrw(ticker.trade_price)} KRW</span>
                  <strong class="${tickerTone}">${formatSignedPercent(ticker.signed_change_rate)}</strong>
                </div>`
              : `<div class="ticker-line muted">현재가 표시 대기</div>`
          }
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
  const readinessColor = info.tone === "alert" ? "#c94f4f" : info.tone === "warn" ? "#c9891b" : "#1b8a8f";
  $("readinessValue").innerHTML = `<strong>${Math.round(info.readiness)}</strong><span>/100</span>`;
  $("readinessValue").style.setProperty("--readiness-progress", `${Math.round(info.readiness)}%`);
  $("readinessValue").style.setProperty("--readiness-color", readinessColor);
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
  renderDemoStage();
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

    const [healthResult, forecastResult, patternResult, tickerResult, radarResults] = await Promise.all([
      fetchOptional("/api/health"),
      fetchOptional(`/api/score-forecast?market=${encodeURIComponent(market)}&days=200`),
      fetchOptional(
        `/api/knn-pattern?market=${encodeURIComponent(market)}&window=10&horizon=30&k=10&metric=raw`,
      ),
      fetchOptional(`/api/ticker?markets=${MARKETS.map(encodeURIComponent).join(",")}`),
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
    if (tickerResult.error) state.errors.ticker = tickerResult.error;
    if (radarResults.some((result) => result.error)) state.errors.radar = true;

    state.health = healthResult.data;
    state.overview = overview;
    state.forecast = forecastResult.data;
    state.pattern = patternResult.data;
    state.ticker = tickerResult.data;
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
  state.virtualOrderLog = null;
  loadDashboard();
});

$("refreshBtn").addEventListener("click", loadDashboard);
$("demoAutoBtn").addEventListener("click", runDemoSequence);

document.addEventListener("click", (event) => {
  const virtualSubmit = event.target.closest("[data-virtual-submit]");
  if (virtualSubmit) {
    event.preventDefault();
    const mode = state.intentMode === "sell" ? "sell" : "buy";
    const label = mode === "sell" ? "가상 매도" : "가상 매수";
    const amount = String(state.virtualQuantity || "").trim() || "미입력";
    state.intentMode = mode;
    state.virtualOrderLog = {
      title: `${label} ${amount} 입력 후 차단`,
      copy: "화면 안에서 전송 시도만 기록하고 Decision Pause로 전환했습니다. Upbit 주문 API, API Key, Secret Key는 사용하지 않습니다.",
    };
    activateDecisionPause();
    return;
  }

  const openPauseButton = event.target.closest("[data-open-pause]");
  if (openPauseButton) {
    event.preventDefault();
    activateDecisionPause();
    return;
  }

  const intentButton = event.target.closest("[data-intent-mode]");
  if (intentButton) {
    clearDemoTimers();
    const mode = intentButton.getAttribute("data-intent-mode");
    state.demoScriptIndex = mode === "buy" ? 1 : mode === "sell" ? 5 : 0;
    if (mode !== state.intentMode) state.virtualOrderLog = null;
    setIntentMode(mode, 0);
    return;
  }

  const button = event.target.closest("[data-check-id]");
  if (button) {
    const id = button.getAttribute("data-check-id");
    state.pauseChecks[id] = !state.pauseChecks[id];
    if (state.overview) {
      renderReadiness();
      renderPauseChecklist();
    }
    renderDemoStage();
    return;
  }

  const marketCard = event.target.closest("[data-market]");
  if (!marketCard) return;
  const market = marketCard.getAttribute("data-market");
  if (market === state.market) return;
  state.market = market;
  state.virtualOrderLog = null;
  $("marketSelect").value = market;
  loadDashboard();
});

document.addEventListener("input", (event) => {
  if (event.target.id !== "virtualQuantityInput") return;
  state.virtualQuantity = event.target.value;
});

loadDashboard();
