const state = {
  languages: [],
  session: null,
  workspace: null,
  activeModule: null,
  activeCourseUnitCode: null,
  activeStudentLectureSessionId: null,
  activeStudentQuizId: null,
  activeLecturerRoomCode: null,
  activeLecturerQuizId: null,
  activeLecturerSessionId: null,
  showLectureSessionComposer: false,
  activeResourceId: null,
  chatOpen: false,
  resourceTranslations: {},
  chatResult: null,
  notificationsFired: new Set(),
  notificationCheckInterval: null,
};

const STUDENT_MODULE_ALIASES = {
  profile: "profile",
  results: "results",
  fees_info: "fees_info",
  my_timetable: "my_timetable",
  e_learning_centre: "e_learning_centre",
  study_planner: "study_planner",
  quiz_centre: "quiz_centre",
  my_registration: "my_registration",
  elearning_dashboard: "e_learning_centre",
  elearning_profile: "profile",
  my_examinations: "quiz_centre",
  announcements: "announcements",
  library: "library",
  feedback_to_lecturer: "feedback_to_lecturer",
};

const LECTURER_MODULE_ALIASES = {
  my_courses: "virtual_lecturer_rooms",
  todays_classes: "todays_classes",
  uploaded_resources: "upload_resources",
  student_questions: "student_feedback",
  virtual_lecturer_rooms: "virtual_lecturer_rooms",
  upload_resources: "upload_resources",
  quiz_generator: "quiz_generator",
  quiz_review: "quiz_review",
  announcements: "announcements",
  student_feedback: "student_feedback",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setHtml(id, value) {
  document.getElementById(id).innerHTML = value;
}

function showAuthMessage(id, message, tone = "success") {
  const element = document.getElementById(id);
  element.textContent = message;
  element.classList.remove("hidden", "is-success", "is-error");
  element.classList.add(`is-${tone}`);
}

function hideAuthMessage(id) {
  const element = document.getElementById(id);
  element.textContent = "";
  element.classList.add("hidden");
  element.classList.remove("is-success", "is-error");
}

function showAppMessage(message, tone = "success") {
  const element = document.getElementById("app-message");
  element.textContent = message;
  element.classList.remove("hidden", "is-success", "is-error");
  element.classList.add(`is-${tone}`);
}

function hideAppMessage() {
  const element = document.getElementById("app-message");
  element.textContent = "";
  element.classList.add("hidden");
  element.classList.remove("is-success", "is-error");
}

async function requestJson(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, {
    headers,
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
}

function showAuthenticated() {
  document.getElementById("auth-stage").classList.add("hidden");
  document.getElementById("app-stage").classList.remove("hidden");
  document.getElementById("chat-fab").classList.toggle("hidden", !state.session);
}

function showLoggedOut() {
  document.getElementById("auth-stage").classList.remove("hidden");
  document.getElementById("app-stage").classList.add("hidden");
  document.getElementById("chat-fab").classList.add("hidden");
  document.getElementById("chat-drawer").classList.add("hidden");
}

function fillLanguageOptions(selectedCode = "") {
  return state.languages
    .map(
      (language) =>
        `<option value="${escapeHtml(language.code)}" ${
          language.code === selectedCode ? "selected" : ""
        }>${escapeHtml(language.name)} (${escapeHtml(language.code)})</option>`,
    )
    .join("");
}

function fillPreferredLanguageOptions(selectedCode = "") {
  return `
    <option value="" ${selectedCode ? "" : "selected"}>Auto</option>
    ${fillLanguageOptions(selectedCode)}
  `;
}

function fillLecturerCourseOptions(selectedCode = currentCourseCode()) {
  const courses = state.workspace?.courses || [];
  if (!courses.length && selectedCode) {
    return `<option value="${escapeHtml(selectedCode)}" selected>${escapeHtml(selectedCode)}</option>`;
  }
  return courses
    .map((course) => {
      const courseCode = course.course_code || "";
      const label = [courseCode, course.title || ""].filter(Boolean).join(" - ");
      return `<option value="${escapeHtml(courseCode)}" ${
        courseCode === selectedCode ? "selected" : ""
      }>${escapeHtml(label || courseCode)}</option>`;
    })
    .join("");
}

function fillStudentCourseUnitOptions(selectedCode = currentCourseCode()) {
  const courses = state.workspace?.courses || [];
  if (!courses.length && selectedCode) {
    return `<option value="${escapeHtml(selectedCode)}" selected>${escapeHtml(selectedCode)}</option>`;
  }
  return courses
    .map((course) => {
      const courseCode = course.course_code || "";
      const label = [courseCode, course.title || ""].filter(Boolean).join(" - ");
      return `<option value="${escapeHtml(courseCode)}" ${
        courseCode === selectedCode ? "selected" : ""
      }>${escapeHtml(label || courseCode)}</option>`;
    })
    .join("");
}

function fillCourseResourceOptions(resources, selectedResourceId = "") {
  return resources
    .map(
      (resource) => `
        <option value="${escapeHtml(resource.resource_id)}" ${
          resource.resource_id === selectedResourceId ? "selected" : ""
        }>${escapeHtml(resource.material_label || resource.title || resource.resource_id)}</option>
      `,
    )
    .join("");
}

function languageName(code) {
  if (!code) {
    return "Auto";
  }
  const match = state.languages.find((language) => language.code === code);
  return match ? match.name : code;
}

function currentCourseCode() {
  return state.workspace?.selected_course_code || state.session?.default_course_code || "";
}

function currentCourse() {
  const selectedCourseCode = currentCourseCode();
  return (
    state.workspace?.selected_course ||
    (state.workspace?.courses || []).find((course) => course.course_code === selectedCourseCode) ||
    null
  );
}

function currentRoom() {
  const selectedCourseCode = currentCourseCode();
  return (
    state.workspace?.selected_room ||
    (state.workspace?.virtual_rooms || []).find((room) => room.course_code === selectedCourseCode) ||
    null
  );
}

function currentResource() {
  if (!state.activeResourceId) {
    return null;
  }
  return (state.workspace?.resources || []).find(
    (resource) => resource.resource_id === state.activeResourceId,
  ) || null;
}

function currentStudentLectureSession() {
  if (!state.activeStudentLectureSessionId) {
    return null;
  }
  return (
    (state.workspace?.lecture_sessions || []).find(
      (session) => session.session_id === state.activeStudentLectureSessionId,
    ) || null
  );
}

function currentStudentQuiz() {
  if (!state.activeStudentQuizId) {
    return null;
  }
  return (state.workspace?.quizzes || []).find((quiz) => quiz.quiz_id === state.activeStudentQuizId) || null;
}

function currentLecturerQuiz() {
  if (!state.activeLecturerQuizId) {
    return null;
  }
  return (state.workspace?.quizzes || []).find((quiz) => quiz.quiz_id === state.activeLecturerQuizId) || null;
}

function currentLectureSession() {
  if (!state.activeLecturerSessionId) {
    return null;
  }
  return (
    (state.workspace?.lecture_sessions || []).find(
      (session) => session.session_id === state.activeLecturerSessionId,
    ) || null
  );
}

function currentChatContext() {
  const resource = currentResource();
  const lectureSession = currentStudentLectureSession();
  return {
    courseCode: resource?.course_code || lectureSession?.course_code || currentCourseCode(),
    resourceId: resource?.resource_id || null,
    label: resource?.title || lectureSession?.title || currentCourseCode() || "Current course",
    topic: resource?.topic || lectureSession?.topic || null,
  };
}

function isElearningModule(module = state.activeModule) {
  if (state.session?.role !== "student") {
    return false;
  }
  return [
    "elearning_dashboard",
    "e_learning_centre",
    "quiz_centre",
    "my_examinations",
    "study_planner",
    "elearning_profile",
  ].includes(module);
}

function isLearningRegistrationModule(module = state.activeModule) {
  return ["my_registration", "my_timetable"].includes(module);
}

function activeShell() {
  return isElearningModule() ? "elearning" : "academica";
}

function displayRegistrationNumber() {
  return (
    state.workspace?.registration_number ||
    state.session?.registration_number ||
    state.session?.student_id ||
    state.session?.lecturer_id ||
    ""
  );
}

function displayUserName() {
  return state.session?.display_name || state.session?.username || "User";
}

function displayUserLine() {
  if (state.session?.role === "student") {
    return `${displayUserName()} :: ${displayRegistrationNumber()}`;
  }
  return `${displayUserName()} :: ${state.session?.lecturer_id || "STAFF"}`;
}

function renderAcademicaLogo() {
  return `
    <div class="academica-logo" aria-label="Academica ERP">
      <span class="academica-dots" aria-hidden="true"><i></i><i></i><i></i></span>
      <strong>ACADEMICA</strong>
      <em>ERP</em>
    </div>
  `;
}

function renderStudentAvatar() {
  const initials = displayUserName()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "IU";
  return `<div class="erp-avatar" aria-label="Student avatar">${escapeHtml(initials)}</div>`;
}

function renderTopSearch() {
  return `
    <form class="portal-search" role="search">
      <input type="search" placeholder="Search" aria-label="Search">
      <button type="button" aria-label="Search">&#128269;</button>
    </form>
  `;
}

function erpNavButton({ module, action, label, icon = "", activeWhen = null, child = false }) {
  const isActive = activeWhen ? activeWhen() : state.activeModule === module || (!state.activeModule && module === "profile");
  const attrs = action
    ? `data-action="${escapeHtml(action)}"`
    : `data-module="${escapeHtml(module)}"`;
  return `
    <button type="button" class="erp-menu-item${child ? " erp-menu-item--child" : ""}${isActive ? " is-active" : ""}" ${attrs}>
      <span class="erp-menu-icon">${icon}</span>
      <span>${escapeHtml(label)}</span>
      ${child ? "" : `<span class="erp-menu-caret">&#8250;</span>`}
    </button>
  `;
}

function renderAcademicaSidebar() {
  if (state.session?.role === "lecturer") {
    const items = [
      { module: "my_courses", label: "My Courses", icon: "&#9638;" },
      { module: "todays_classes", label: "Today's Classes", icon: "&#9636;" },
      { module: "upload_resources", label: "Resources Centre", icon: "&#9635;" },
      { module: "quiz_generator", label: "Quiz Generator", icon: "&#10003;" },
      { module: "quiz_review", label: "Quiz Review", icon: "&#10003;" },
      { module: "student_feedback", label: "Student Feedback", icon: "&#9993;" },
      { module: "announcements", label: "Notifications", icon: "&#9888;" },
    ];
    return `
      <aside class="erp-sidebar">
        <div class="erp-logo-card">${renderAcademicaLogo()}</div>
        <nav class="erp-menu" aria-label="Lecturer menu">
          ${items.map((item) => erpNavButton(item)).join("")}
        </nav>
      </aside>
    `;
  }

  const learningRegistrationOpen = isLearningRegistrationModule();

  return `
    <aside class="erp-sidebar">
      <div class="erp-logo-card">${renderAcademicaLogo()}</div>
      <nav class="erp-menu" aria-label="Student menu">
        ${erpNavButton({ module: "announcements", label: "Notifications", icon: "&#9888;" })}
        ${erpNavButton({ module: "profile", label: "My Profile", icon: "&#9787;" })}
        ${erpNavButton({ module: "elearning_dashboard", label: "E-learning Centre", icon: "&#9673;", activeWhen: () => isElearningModule() })}
        ${erpNavButton({ module: "feedback_to_lecturer", label: "Feedback to Lecturer", icon: "&#9993;" })}
        <div class="erp-menu-group${learningRegistrationOpen ? " is-open" : ""}">
          ${erpNavButton({ module: "my_registration", label: "Learning & Registration", icon: "&#9632;", activeWhen: () => learningRegistrationOpen })}
          ${learningRegistrationOpen ? `
            ${erpNavButton({ module: "my_registration", label: "Courses & Registration", icon: "&#9636;", child: true })}
            ${erpNavButton({ module: "my_registration", label: "Retake Registration", icon: "&#8644;", child: true })}
            ${erpNavButton({ module: "my_timetable", label: "Timetable Info", icon: "&#9635;", child: true })}
          ` : ""}
        </div>
        ${erpNavButton({ module: "fees_info", label: "Fees Information", icon: "&#9637;" })}
        <div class="erp-menu-group${state.activeModule === "results" ? " is-open" : ""}">
          ${erpNavButton({ module: "results", label: "Results Centre", icon: "&#10038;" })}
          ${state.activeModule === "results" ? `
            ${erpNavButton({ module: "results", label: "Exam Results", icon: "&#9635;", child: true })}
            ${erpNavButton({ module: "results", label: "Coursework Results", icon: "&#9635;", child: true })}
          ` : ""}
        </div>
        ${erpNavButton({ module: "library", label: "Library Centre", icon: "&#9632;" })}
      </nav>
    </aside>
  `;
}

function renderElearningSidebar() {
  const items = [
    { action: "go-home", label: "ERP Portal Home", icon: "&#8962;", activeWhen: () => false },
    { module: "elearning_dashboard", label: "My Dashboard", icon: "&#9634;" },
    { module: "e_learning_centre", label: "My Digital Classes", icon: "&#9787;" },
    { module: "my_examinations", label: "My Examinations", icon: "&#9635;", activeWhen: () => state.activeModule === "quiz_centre" || state.activeModule === "my_examinations" },
    { module: "feedback_to_lecturer", label: "Feedback to Lecturer", icon: "&#9993;" },
    { module: "elearning_profile", label: "My Profile", icon: "&#9790;" },
    { module: "study_planner", label: "User Guide", icon: "&#9635;" },
  ];
  return `
    <aside class="elearn-sidebar">
      <div class="elearn-brand">
        <span class="elearn-seal">IU</span>
        <strong>E-LEARNING</strong>
      </div>
      <p class="elearn-menu-label">MAIN MENU</p>
      <nav class="elearn-menu" aria-label="E-learning menu">
        ${items.map((item) => erpNavButton(item).replaceAll("erp-menu", "elearn-menu")).join("")}
      </nav>
    </aside>
  `;
}

function renderPortalChrome() {
  if (activeShell() === "elearning") {
    return `
      <div class="portal-chrome portal-chrome--elearning">
        <header class="elearn-topbar">
          <button type="button" class="icon-button" aria-label="Open menu">&#9776;</button>
          <button type="button" class="icon-button" aria-label="Fullscreen">&#9974;</button>
          <div class="elearn-topbar-actions">
            <span class="chat-pill">0 Chats</span>
            <button type="button" class="icon-button" aria-label="Messages">&#9993;</button>
            <button type="button" class="icon-button" aria-label="Notifications">&#9888;</button>
            ${renderStudentAvatar()}
          </div>
        </header>
        ${renderElearningSidebar()}
      </div>
    `;
  }

  return `
    <div class="portal-chrome portal-chrome--academica">
      <header class="erp-topbar">
        <button type="button" class="erp-hamburger" aria-label="Open menu">&#9776;</button>
        <div class="erp-topbar-spacer"></div>
        ${renderTopSearch()}
        <button type="button" class="erp-top-icon" aria-label="Notifications">&#9888;</button>
        <button type="button" class="erp-top-icon" aria-label="User">&#9787;</button>
      </header>
      ${renderAcademicaSidebar()}
    </div>
  `;
}

function detailRows(rows) {
  return rows
    .map(
      (row) => `
        <div class="detail-row">
          <span>${escapeHtml(row.label)}</span>
          <strong>${escapeHtml(row.value)}</strong>
        </div>
      `,
    )
    .join("");
}

function renderQuickTile(tile) {
  return `
    <button type="button" class="quick-tile" data-module="${escapeHtml(tile.module)}">
      <div class="tile-icon">${escapeHtml(tile.icon_text || "--")}</div>
      <div class="tile-label">${escapeHtml(tile.label)}</div>
      <div class="tile-value">${escapeHtml(tile.value || "")}</div>
      <div class="tile-subtitle">${escapeHtml(tile.subtitle || "")}</div>
    </button>
  `;
}

function renderServiceTile(tile) {
  return `
    <button type="button" class="service-card" data-module="${escapeHtml(tile.module)}">
      <div class="service-icon">${escapeHtml(tile.icon_text || "--")}</div>
      <div>
        <div class="service-label">${escapeHtml(tile.label)}</div>
        <div class="service-subtitle">${escapeHtml(tile.description || tile.subtitle || "")}</div>
      </div>
      <div class="service-more">&#8250;</div>
    </button>
  `;
}

function workspaceStats() {
  const workspace = state.workspace || {};
  if (state.session?.role === "lecturer") {
    return [
      { label: "Rooms", value: (workspace.virtual_rooms || []).length },
      { label: "Resources", value: (workspace.resources || []).length },
      { label: "Sessions", value: (workspace.lecture_sessions || []).length },
      { label: "Quizzes", value: (workspace.quizzes || []).length },
    ];
  }
  return [
    { label: "Courses", value: (workspace.courses || []).length },
    { label: "Resources", value: (workspace.resources || []).length },
    { label: "Lectures", value: (workspace.lecture_sessions || []).length },
    { label: "Quizzes", value: (workspace.quizzes || []).length },
  ];
}

function renderWorkspaceStat(stat) {
  return `
    <article class="hero-stat">
      <strong class="hero-stat-value">${escapeHtml(stat.value)}</strong>
      <span class="hero-stat-label">${escapeHtml(stat.label)}</span>
    </article>
  `;
}

function headerChips() {
  const chips = [];
  const focusLabel = currentCourse()?.title || currentRoom()?.title || currentCourseCode();
  if (focusLabel) {
    chips.push(`Current focus: ${focusLabel}`);
  }
  if (state.session?.role === "lecturer") {
    chips.push(`Course support ready for room resources`);
  } else {
    chips.push(`Course support ready for lecture notes`);
  }
  return chips;
}

function renderHeader() {
  return renderPortalChrome();
}

function renderErpStudentBar(text = displayUserLine()) {
  return `
    <div class="erp-user-strip">
      <strong>${escapeHtml(text)}</strong>
      <button type="button" class="erp-logout" data-action="logout">Sign Out</button>
    </div>
  `;
}

function renderLegacyPanel({ title, icon = "&#9636;", body, extraClass = "" }) {
  return `
    <section class="legacy-panel ${extraClass}">
      <div class="legacy-panel-inner">
        <div class="legacy-panel-title">
          <span class="legacy-title-icon">${icon}</span>
          <strong>${escapeHtml(title)}</strong>
        </div>
        ${body}
      </div>
    </section>
  `;
}

function renderLegacyTable({ columns, rows, empty = "No data available in table", highlightFirst = false }) {
  const bodyRows = rows.length
    ? rows
        .map(
          (row, index) => `
            <tr class="${highlightFirst && index === 0 ? "is-highlighted" : ""}">
              ${row.map((cell) => `<td>${cell == null ? "" : escapeHtml(cell)}</td>`).join("")}
            </tr>
          `,
        )
        .join("")
    : `<tr><td colspan="${columns.length}" class="legacy-empty-cell">${escapeHtml(empty)}</td></tr>`;
  return `
    <table class="legacy-table">
      <thead>
        <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
      </thead>
      <tbody>${bodyRows}</tbody>
    </table>
  `;
}

function renderLegacyTableRaw({ columns, rowsHtml, empty = "No data available in table" }) {
  return `
    <table class="legacy-table">
      <thead>
        <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
      </thead>
      <tbody>${rowsHtml || `<tr><td colspan="${columns.length}" class="legacy-empty-cell">${escapeHtml(empty)}</td></tr>`}</tbody>
    </table>
  `;
}

function renderDataToolbar({ showEntries = true, search = true } = {}) {
  return `
    <div class="legacy-data-toolbar">
      ${showEntries ? `
        <label class="legacy-show-entries">
          <span>Show</span>
          <select><option>10</option><option>25</option><option>50</option></select>
          <span>entries</span>
        </label>
      ` : "<span></span>"}
      ${search ? `
        <label class="legacy-search-inline">
          <span>Search:</span>
          <input type="search">
        </label>
      ` : ""}
    </div>
  `;
}

function renderErpSummaryCards(items) {
  return `
    <div class="erp-summary-grid">
      ${items
        .map(
          (item) => `
            <article class="erp-summary-card">
              <span>${escapeHtml(item.label)}</span>
              <strong>${escapeHtml(item.value)}</strong>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderHome() {
  const user = state.session || {};
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const dateStr = now.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return `
    <section class="home-stage">
      <div class="welcome-banner">
        <div class="welcome-info">
          <p class="welcome-kicker">Welcome back</p>
          <h2 class="welcome-name">${escapeHtml(user.display_name || "User")}</h2>
          <p class="welcome-role">${escapeHtml(user.role === "lecturer" ? "Lecturer · Kampala Campus" : (user.program || "Student") + " · Kampala Campus")}</p>
        </div>
        <div class="portal-datetime">
          <div class="datetime-time">${escapeHtml(timeStr)}</div>
          <div class="datetime-date">${escapeHtml(dateStr)}</div>
        </div>
      </div>
      <section class="dashboard-panel">
        <div class="panel-head">
          <div>
            <p class="section-kicker">Quick Info</p>
            <h2 class="section-title">At a glance</h2>
          </div>
          <p class="panel-copy">Key counts and status cues for the current workspace.</p>
        </div>
        <div class="tile-grid">
        ${(state.workspace?.quick_info_tiles || []).map(renderQuickTile).join("")}
        </div>
      </section>

      <section class="dashboard-panel">
        <div class="panel-head">
          <div>
            <p class="section-kicker">Services</p>
            <h2 class="section-title">Open a workflow</h2>
          </div>
          <p class="panel-copy">Jump directly into the modules used most often in this role.</p>
        </div>
        <div class="service-grid">
          ${(state.workspace?.service_tiles || []).map(renderServiceTile).join("")}
        </div>
      </section>
    </section>
  `;
}

function renderHome() {
  if (state.session?.role === "student") {
    return renderStudentProfileErp(state.workspace || {});
  }

  const workspace = state.workspace || {};
  return `
    <section class="erp-page">
      ${renderErpStudentBar(displayUserLine())}
      ${renderLegacyPanel({
        title: "LECTURER DASHBOARD",
        icon: "&#9636;",
        body: `
          ${renderErpSummaryCards(workspaceStats())}
          <div class="legacy-table-wrap">
            ${renderLegacyTable({
              columns: ["#", "Course", "Room", "Schedule", "Enrolled", "Resources"],
              rows: (workspace.virtual_rooms || []).map((room, index) => [
                index + 1,
                `${room.course_code} - ${room.title}`,
                room.room || "-",
                [room.day, room.time].filter(Boolean).join(" ") || "-",
                room.enrolled || "-",
                room.resource_count || 0,
              ]),
            })}
          </div>
        `,
      })}
    </section>
  `;
}

function moduleTitle(module) {
  const explicitTitles = {
    elearning_dashboard: "My Dashboard",
    elearning_profile: "My Profile",
    my_examinations: "My Examinations",
    my_registration: "Courses & E-Content Centre",
    fees_info: "Fees Information",
    results: "Exam Results",
  };
  if (explicitTitles[module]) {
    return explicitTitles[module];
  }
  const allTiles = [
    ...(state.workspace?.quick_info_tiles || []),
    ...(state.workspace?.service_tiles || []),
  ];
  const tile = allTiles.find((entry) => entry.module === module);
  return tile ? tile.label : "Module";
}

function moduleDescription(module) {
  const descriptions = {
    announcements: "Review the latest notices tied to the current role and course context.",
    e_learning_centre: "Browse course units, open lecture sessions, and move into attached study resources.",
    feedback_to_lecturer: "Send difficulty areas and comments back to the teaching side in a structured way.",
    library: "Open indexed course material, translated PDFs, and related lecture resources from one screen.",
    my_timetable: "Generate study time blocks based on the hours you can commit this week.",
    quiz_centre: "Attempt prepared quizzes and review past performance in the current course.",
    quiz_generator: "Create quizzes from uploaded course notes and prepare them for student attempts.",
    quiz_review: "Inspect attempts, pass rates, and question-level performance after quizzes go live.",
    results: "Review student-facing assessment results and recent outcome summaries.",
    student_feedback: "Track what students are struggling with and where extra explanation is needed.",
    study_planner: "Refresh weekly recommendations and next actions from the current workload.",
    upload_resources: "Create lecture sessions, attach files, and keep every room up to date.",
    virtual_lecturer_rooms: "See course-room status, enrollment, and recent teaching activity before drilling in.",
  };
  const activeKey = effectiveModule(module) || module;
  return descriptions[activeKey] || "Manage this workspace area from one place.";
}

function resourcePdfUrl(resourceId, translate = true) {
  const params = new URLSearchParams({
    student_id: state.session?.student_id || "",
    translate: translate ? "true" : "false",
  });
  return `/student/resources/${encodeURIComponent(resourceId)}/pdf?${params.toString()}`;
}

function openResourcePdf(resourceId, translate = true) {
  const resource = (state.workspace?.resources || []).find(
    (entry) => entry.resource_id === resourceId,
  );
  state.activeResourceId = resourceId;
  renderAuthenticatedApp();
  const popup = window.open(resourcePdfUrl(resourceId, translate), "_blank", "noopener");
  if (!popup) {
    throw new Error("The PDF window was blocked by the browser.");
  }
  showAppMessage(
    `${resource?.material_label || resource?.title || "Lecture note"} opened in a new window ${
      translate ? "with translation" : "without translation"
    }.`,
    "success",
  );
}

function effectiveModule(module) {
  if (!state.session) {
    return null;
  }
  return state.session.role === "lecturer"
    ? LECTURER_MODULE_ALIASES[module] || module
    : STUDENT_MODULE_ALIASES[module] || module;
}

function renderModuleNav() {
  const user = state.session || {};
  const activeModule = state.activeModule;

  const navBtn = (module, label) =>
    `<button type="button" class="module-nav-btn${activeModule === module ? " is-active" : ""}" data-module="${escapeHtml(module)}">${escapeHtml(label)}</button>`;

  const studentItems = [
    ["profile", "My Profile"],
    ["results", "Results"],
    ["fees_info", "Fees & Finance"],
    ["my_timetable", "Timetable"],
    ["e_learning_centre", "E-Learning Centre"],
    ["study_planner", "Study Planner"],
    ["quiz_centre", "Quiz Centre"],
    ["my_registration", "Registration"],
    ["announcements", "Notices"],
    ["library", "Library"],
    ["feedback_to_lecturer", "Feedback"],
  ];

  const lecturerItems = [
    ["my_courses", "My Courses"],
    ["todays_classes", "Today's Classes"],
    ["upload_resources", "Upload Resources"],
    ["quiz_generator", "Quiz Generator"],
    ["quiz_review", "Quiz Review"],
    ["announcements", "Notices"],
    ["student_feedback", "Student Feedback"],
  ];

  const items = user.role === "lecturer" ? lecturerItems : studentItems;

  return `
    <nav class="module-nav-strip" aria-label="Module shortcuts">
      <button type="button" class="module-nav-btn module-nav-btn--home${!activeModule ? " is-active" : ""}" data-action="go-home">&#8962; Dashboard</button>
      ${items.map(([module, label]) => navBtn(module, label)).join("")}
    </nav>
  `;
}

function renderModule() {
  const module = effectiveModule(state.activeModule);
  if (!module) {
    return renderHome();
  }

  const body =
    state.session.role === "lecturer"
      ? renderLecturerModule(module)
      : renderStudentModule(module);

  if (state.session?.role === "student" && state.activeModule === "profile") {
    return body;
  }

  if (activeShell() === "elearning") {
    return `
      <section class="elearn-page">
        ${body}
      </section>
    `;
  }

  return `
    <section class="erp-page">
      ${renderErpStudentBar(displayUserLine())}
      ${body}
    </section>
  `;
}

function renderRoomCards(
  rooms,
  { clickable = false, activeCourseCode = "", clickAction = "open-course-room" } = {},
) {
  if (!rooms.length) {
    return `<div class="empty-state">No virtual lecturer rooms are available for the selected course.</div>`;
  }
  return rooms
    .map(
      (room) => `
        <${
          clickable ? "button type=\"button\"" : "article"
        } class="detail-card room-card ${room.course_code === activeCourseCode ? "is-active" : ""}" ${
          clickable
            ? `data-action="${escapeHtml(clickAction)}" data-course-code="${escapeHtml(room.course_code)}"`
            : ""
        }>
          <h3>${escapeHtml(room.title)}</h3>
          <div class="helper">${escapeHtml(
            [room.course_code, room.year_of_study, room.semester].filter(Boolean).join(" | "),
          )}</div>
          <div class="helper">${escapeHtml(
            room.enrolled
              ? `${room.enrolled} student(s) enrolled${room.room ? ` | ${room.room}` : ""}`
              : room.lecturer
                ? `Lecturer: ${room.lecturer}`
                : room.room || "",
          )}</div>
          <div class="helper">${escapeHtml(
            room.resource_count ? `${room.resource_count} lecture PDF(s) available.` : "No uploaded resource yet.",
          )}</div>
          <div class="helper">${escapeHtml(
            room.latest_resource ? `Latest resource: ${room.latest_resource}` : "No uploaded resource yet.",
          )}</div>
        </${clickable ? "button" : "article"}>
      `,
    )
    .join("");
}

function renderResourceCards(
  resources,
  { allowSelect = true, pdfActions = false, emptyMessage = "No resources are available for the selected course." } = {},
) {
  if (!resources.length) {
    return `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
  }
  return resources
    .map(
      (resource) => `
        <article class="resource-card">
          <div class="resource-header">
            <div>
              <h3>${escapeHtml(resource.material_label || resource.title)}</h3>
              <div class="resource-subtitle">${escapeHtml(
                [
                  resource.course_code,
                  resource.topic || null,
                  resource.week || null,
                ]
                  .filter(Boolean)
                  .join(" | "),
              )}</div>
            </div>
            <span class="chip">${escapeHtml(resource.course_code)}</span>
          </div>
          <div class="helper">${escapeHtml(resource.excerpt || "No excerpt available.")}</div>
          ${
            pdfActions
              ? `<div class="row-actions">
                  <button
                    type="button"
                    class="primary-button"
                    data-action="open-resource-pdf"
                    data-resource-id="${escapeHtml(resource.resource_id)}"
                    data-translate="true"
                  >
                    Translated PDF
                  </button>
                  <button
                    type="button"
                    class="ghost-button"
                    data-action="open-resource-pdf"
                    data-resource-id="${escapeHtml(resource.resource_id)}"
                    data-translate="false"
                  >
                    Open original
                  </button>
                </div>`
              : allowSelect
              ? `<div class="row-actions">
                  <button type="button" class="ghost-button" data-action="open-resource" data-resource-id="${escapeHtml(
                    resource.resource_id,
                  )}">Open</button>
                </div>`
              : ""
          }
        </article>
      `,
    )
    .join("");
}

function renderStudentAttachmentCards(attachments) {
  if (!attachments.length) {
    return `<div class="empty-state">No files have been attached to this lecture session yet.</div>`;
  }
  return attachments
    .map(
      (attachment) => `
        <article class="resource-card attachment-card">
          <div class="resource-header">
            <div>
              <h3>${escapeHtml(attachment.title)}</h3>
              <div class="resource-subtitle">${escapeHtml(
                [
                  attachment.original_filename || null,
                  attachment.indexed ? "Indexed" : "Original only",
                ]
                  .filter(Boolean)
                  .join(" | "),
              )}</div>
            </div>
            <span class="chip">${escapeHtml(attachment.course_code)}</span>
          </div>
          <div class="helper">${escapeHtml(attachment.excerpt || "No excerpt available.")}</div>
          <div class="row-actions">
            <button
              type="button"
              class="primary-button"
              data-action="open-resource-pdf"
              data-resource-id="${escapeHtml(attachment.resource_id)}"
              data-translate="true"
              ${attachment.translation_available ? "" : "disabled"}
            >
              ${attachment.translation_available ? "Translated PDF" : "No translation"}
            </button>
            <button
              type="button"
              class="ghost-button"
              data-action="open-resource-pdf"
              data-resource-id="${escapeHtml(attachment.resource_id)}"
              data-translate="false"
            >
              Open original
            </button>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderStudentLectureTabs(sessions, activeSessionId = "") {
  if (!sessions.length) {
    return `<div class="empty-state">No lecture sessions are available for this course unit yet.</div>`;
  }

  return `
    <div class="lecture-tab-list" role="tablist" aria-label="Lecture list">
      ${sessions
        .map(
          (session) => `
            <button
              type="button"
              class="lecture-tab ${session.session_id === activeSessionId ? "is-active" : ""}"
              data-action="open-student-lecture-session"
              data-session-id="${escapeHtml(session.session_id)}"
              aria-pressed="${session.session_id === activeSessionId ? "true" : "false"}"
            >
              <span class="lecture-tab-title">${escapeHtml(session.title || `Lecture ${session.lecture_number || ""}`.trim())}</span>
              <span class="lecture-tab-meta">${escapeHtml(
                [session.date_or_week || null, `${session.attachment_count || 0} resource(s)`]
                  .filter(Boolean)
                  .join(" | "),
              )}</span>
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderStudentLectureDirectory(workspace) {
  const sessions = workspace.lecture_sessions || [];
  return `
    <section class="elearn-card elearn-lecture-card">
      <div class="elearn-section-head">
        <div>
          <p class="section-kicker">Lectures</p>
          <h2>Select one lecture</h2>
        </div>
        <div class="helper">
          ${escapeHtml(
            sessions.length
              ? `${sessions.length} lecture session(s) are ready for this course unit.`
              : "No lecture sessions are available for this course unit yet.",
          )}
        </div>
      </div>
      ${renderStudentLectureTabs(sessions)}
    </section>
  `;
}

function renderStudentLectureSessionDetail(workspace, session) {
  const sessions = workspace.lecture_sessions || [];
  return `
    <section class="elearn-card elearn-lecture-detail">
      <div class="elearn-section-head">
        <div>
          <p class="section-kicker">Lecture Resources</p>
          <h2>${escapeHtml(session.title || "Lecture")}</h2>
        </div>
        <div class="helper">${escapeHtml(
          [session.topic || null, session.date_or_week || null, session.status || "Delivered"]
            .filter(Boolean)
            .join(" | "),
        )}</div>
      </div>
      <div class="row-actions">
        <button type="button" class="ghost-button" data-action="back-to-lecture-directory">
          Back to lectures
        </button>
      </div>
      ${renderStudentLectureTabs(sessions, session.session_id)}
      ${
        session.notes_text
          ? `<div class="context-banner">${escapeHtml(session.notes_text)}</div>`
          : ""
      }
      ${
        session.status && session.status !== "Delivered"
          ? `<div class="context-banner">This lecture session is marked ${escapeHtml(
              session.status.toLowerCase(),
            )}.</div>`
          : ""
      }
      <section class="elearn-resource-block">
        <div class="elearn-section-head">
          <div>
            <p class="section-kicker">Resources</p>
            <h2>${escapeHtml(`${session.attachment_count || 0} file(s)`)}</h2>
          </div>
        </div>
        <div class="attachment-list">
          ${renderStudentAttachmentCards(session.attachments || [])}
        </div>
      </section>
    </section>
  `;
}

function renderStudentCourseUnits(workspace) {
  const rooms = workspace.virtual_rooms || [];
  return `
    <section class="module-section">
      <div class="section-intro">
        <div>
          <p class="section-kicker">Registered Course Units</p>
          <h3>Open one course unit</h3>
        </div>
        <div class="helper">Each course unit opens its own resource screen.</div>
      </div>
      <div class="resource-list room-grid">
        ${renderRoomCards(rooms, { clickable: true, activeCourseCode: state.activeCourseUnitCode || "" })}
      </div>
    </section>
  `;
}

function renderStudentCourseSelector(workspace) {
  const options = fillStudentCourseUnitOptions();

  if (!options) {
    return "";
  }

  return `
    <label class="picker-field">
      <span>Course unit</span>
      <select id="student-course-unit-select">${options}</select>
    </label>
  `;
}

function renderStudentCourseResourceView(workspace) {
  const selectedCourse = currentCourse();
  const selectedRoom = currentRoom();
  const activeSession = currentStudentLectureSession();
  return `
    <section class="elearn-course-stack">
      <section class="elearn-card elearn-course-card">
      <div class="elearn-section-head">
        <div>
          <p class="section-kicker">Course Unit</p>
          <h2>${escapeHtml(selectedCourse?.title || "Course materials")}</h2>
        </div>
        <div class="helper">${escapeHtml(
          [selectedCourse?.course_code, selectedRoom?.semester, selectedRoom?.lecturer]
            .filter(Boolean)
            .join(" | ") || "Choose a course unit to view its lectures.",
        )}</div>
      </div>
      <div class="resource-toolbar elearn-resource-toolbar">
        ${renderStudentCourseSelector(workspace)}
        <div class="row-actions">
          <button type="button" class="ghost-button" data-action="back-to-course-units">
            Back to course units
          </button>
        </div>
      </div>
      ${
        activeSession
          ? `<div class="context-banner">Course support linked to ${escapeHtml(
              activeSession.title || "the current lecture",
            )}.</div>`
          : ""
      }
      </section>
      ${activeSession ? renderStudentLectureSessionDetail(workspace, activeSession) : renderStudentLectureDirectory(workspace)}
    </section>
  `;
}

function renderLecturerRoomDirectory(workspace) {
  return `
    <section class="module-section">
      <div class="section-intro">
        <div>
          <p class="section-kicker">Lecturer Rooms</p>
          <h3>Open one virtual room</h3>
        </div>
        <div class="helper">Each room opens its teaching details immediately.</div>
      </div>
      <div class="resource-list room-grid">
        ${renderRoomCards(workspace.virtual_rooms || [], {
          clickable: true,
          activeCourseCode: state.activeLecturerRoomCode || "",
          clickAction: "open-lecturer-room",
        })}
      </div>
    </section>
  `;
}

function renderLecturerRoomDetail(workspace) {
  const selectedCourse = currentCourse();
  const selectedRoom = currentRoom();
  const roomSchedule = (workspace.today_schedule || []).filter(
    (entry) => entry.course_code === currentCourseCode(),
  );
  const metrics = [
    { label: "Enrolled Students", value: selectedRoom?.enrolled || "N/A" },
    { label: "Teaching Space", value: selectedRoom?.room || "TBA" },
    {
      label: "Weekly Schedule",
      value: [selectedCourse?.day, selectedCourse?.time].filter(Boolean).join(" | ") || "TBA",
    },
    { label: "Lecture Sessions", value: (workspace.lecture_sessions || []).length || 0 },
    { label: "Indexed Resources", value: (workspace.resources || []).length || 0 },
    { label: "Quiz Sets", value: (workspace.quizzes || []).length || 0 },
    { label: "Student Questions", value: workspace.student_feedback?.total_count || 0 },
  ];

  return `
    <section class="module-section">
      <div class="section-intro">
        <div>
          <p class="section-kicker">Virtual Room</p>
          <h3>${escapeHtml(selectedCourse?.title || "Lecturer room")}</h3>
        </div>
        <div class="helper">${escapeHtml(
          [selectedCourse?.course_code, selectedRoom?.year_of_study, selectedRoom?.semester]
            .filter(Boolean)
            .join(" | ") || "Select a room to view its details.",
        )}</div>
      </div>
      <div class="row-actions">
        <button type="button" class="ghost-button" data-action="back-to-lecturer-rooms">
          Back to rooms
        </button>
        <button type="button" class="primary-button" data-action="open-session-manager">
          Manage lecture sessions
        </button>
      </div>
      <div class="metric-grid">
        ${metrics
          .map(
            (item) => `
              <article class="detail-card metric-card">
                <p class="section-kicker">${escapeHtml(item.label)}</p>
                <h3>${escapeHtml(item.value)}</h3>
              </article>
            `,
          )
          .join("")}
      </div>
      <section class="module-section">
        <div class="section-intro">
          <div>
            <p class="section-kicker">Teaching Activity</p>
            <h3>Schedule and room activity</h3>
          </div>
        </div>
        <div class="resource-list">
          ${
            roomSchedule.length
              ? roomSchedule
                  .map(
                    (entry) => `
                      <article class="detail-card">
                        <h3>${escapeHtml(entry.title)}</h3>
                        <div class="helper">${escapeHtml(
                          [entry.time, entry.location, entry.course_code].filter(Boolean).join(" | "),
                        )}</div>
                      </article>
                    `,
                  )
                  .join("")
              : `
                <article class="detail-card">
                  <h3>${escapeHtml([selectedCourse?.day, selectedCourse?.time].filter(Boolean).join(" | ") || "Weekly schedule")}</h3>
                  <div class="helper">${escapeHtml(
                    selectedRoom?.room
                      ? `Teaching space: ${selectedRoom.room}`
                      : "This room does not have a teaching space assigned yet.",
                  )}</div>
                </article>
              `
          }
          <article class="detail-card">
            <h3>Student feedback</h3>
            <div class="helper">${escapeHtml(
              workspace.student_feedback?.open_count
                ? `${workspace.student_feedback.open_count} open student question(s) in this room.`
                : "No open student questions for this room.",
            )}</div>
            <div class="helper">${escapeHtml(
              workspace.student_feedback?.by_topic?.[0]?.latest_comment || "No recent feedback note yet.",
            )}</div>
          </article>
        </div>
      </section>
      <section class="module-section">
        <div class="section-intro">
          <div>
            <p class="section-kicker">Room Resources</p>
            <h3>Indexed lecture materials</h3>
          </div>
        </div>
        <div class="resource-list">
          ${renderResourceCards(workspace.resources || [], {
            allowSelect: false,
            emptyMessage: "No resources are indexed for this room yet.",
          })}
        </div>
      </section>
    </section>
  `;
}

function renderLecturerAttachmentCards(attachments) {
  if (!attachments.length) {
    return `<div class="empty-state">No files have been attached to this lecture session yet.</div>`;
  }

  return attachments
    .map(
      (attachment) => `
        <article class="resource-card attachment-card">
          <div class="resource-header">
            <div>
              <h3>${escapeHtml(attachment.title)}</h3>
              <div class="resource-subtitle">${escapeHtml(
                [
                  attachment.original_filename || null,
                  attachment.indexed ? "Indexed" : "Stored only",
                ]
                  .filter(Boolean)
                  .join(" | "),
              )}</div>
            </div>
            <span class="chip">${escapeHtml(attachment.course_code)}</span>
          </div>
          <div class="helper">${escapeHtml(
            attachment.index_error || attachment.excerpt || "No preview is available for this attachment.",
          )}</div>
        </article>
      `,
    )
    .join("");
}

function renderLecturerSessionComposer(workspace) {
  return `
    <form id="lecture-session-create-form" class="stack">
      <div class="section-intro">
        <div>
          <p class="section-kicker">New Lecture Session</p>
          <h3>Create the next lecture entry</h3>
        </div>
        <div class="helper">${escapeHtml(currentCourse()?.title || currentCourseCode() || "Current room")}</div>
      </div>
      <div class="detail-grid">
        <label>
          <span>Lecture number</span>
          <input type="number" id="session-lecture-number" min="1" max="99" value="${escapeHtml(
            workspace.next_lecture_number || 1,
          )}" required>
        </label>
        <label>
          <span>Date or week</span>
          <input type="text" id="session-date-or-week" value="${escapeHtml(
            `Week ${workspace.next_lecture_number || 1}`,
          )}" placeholder="Week 4 or 2026-04-03">
        </label>
      </div>
      <label>
        <span>Topic</span>
        <input type="text" id="session-topic" placeholder="Example: ERP workflow mapping" required>
      </label>
      <label>
        <span>Title</span>
        <input type="text" id="session-title" value="${escapeHtml(
          `Lecture ${workspace.next_lecture_number || 1}`,
        )}" data-manual="false" placeholder="Filled from lecture number and topic">
      </label>
      <label>
        <span>Status</span>
        <select id="session-status">
          <option value="Delivered">Delivered</option>
          <option value="Missed">Missed</option>
          <option value="Make-up">Make-up</option>
        </select>
      </label>
      <label>
        <span>Session notes</span>
        <textarea id="session-notes-text" rows="6" placeholder="Add the lecturer notes or a summary for students."></textarea>
      </label>
      <label>
        <span>Attach files</span>
        <input type="file" id="session-create-files" accept=".pdf,.txt,.md,.csv,.json,.html,.docx" multiple>
      </label>
      <div id="session-create-file-list" class="helper">No files selected yet.</div>
      <div class="row-actions">
        <button type="submit" class="primary-button">Create lecture session</button>
        <button type="button" class="ghost-button" data-action="cancel-lecture-session-composer">
          Cancel
        </button>
      </div>
    </form>
  `;
}

function renderLecturerSessionDirectory(workspace) {
  const sessions = workspace.lecture_sessions || [];
  return `
    <section class="module-section">
      <div class="section-intro">
        <div>
          <p class="section-kicker">Course Room</p>
          <h3>${escapeHtml(currentCourse()?.title || "Lecture sessions")}</h3>
        </div>
        <div class="helper">${escapeHtml(
          [currentCourseCode(), currentRoom()?.room, currentRoom()?.semester].filter(Boolean).join(" | "),
        )}</div>
      </div>
      <div class="resource-list room-grid">
        ${renderRoomCards(workspace.virtual_rooms || [], {
          clickable: true,
          activeCourseCode: currentCourseCode(),
          clickAction: "select-upload-room",
        })}
      </div>
      <div class="row-actions">
        <button type="button" class="primary-button" data-action="show-lecture-session-composer">
          New Lecture Session
        </button>
        <button type="button" class="ghost-button" data-action="open-lecturer-room">
          View room detail
        </button>
      </div>
      ${
        state.showLectureSessionComposer
          ? renderLecturerSessionComposer(workspace)
          : ""
      }
      <div class="session-list">
        ${
          sessions.length
            ? sessions
                .map(
                  (session) => `
                    <article class="detail-card session-card">
                      <div class="resource-header">
                        <div>
                          <h3>${escapeHtml(session.title)}</h3>
                          <div class="resource-subtitle">${escapeHtml(
                            [
                              `Lecture ${session.lecture_number}`,
                              session.topic || null,
                              session.date_or_week || null,
                            ]
                              .filter(Boolean)
                              .join(" | "),
                          )}</div>
                        </div>
                        <span class="chip">${escapeHtml(session.status)}</span>
                      </div>
                      <div class="helper">${escapeHtml(
                        session.notes_text
                          ? session.notes_text
                          : "No lecturer notes have been saved for this session yet.",
                      )}</div>
                      <div class="helper">${escapeHtml(
                        `${session.attachment_count || 0} attached file(s) | ${session.indexed_attachment_count || 0} indexed`,
                      )}</div>
                      <div class="row-actions">
                        <button type="button" class="primary-button" data-action="open-lecture-session" data-session-id="${escapeHtml(
                          session.session_id,
                        )}">View session</button>
                        <button type="button" class="ghost-button" data-action="edit-lecture-session" data-session-id="${escapeHtml(
                          session.session_id,
                        )}">Edit notes</button>
                        <button type="button" class="ghost-button" data-action="add-files-lecture-session" data-session-id="${escapeHtml(
                          session.session_id,
                        )}">Add files</button>
                        <button type="button" class="ghost-button" data-action="set-lecture-session-status" data-session-id="${escapeHtml(
                          session.session_id,
                        )}" data-status="${escapeHtml(session.status === "Missed" ? "Make-up" : "Missed")}">${
                          session.status === "Missed" ? "Mark make-up" : "Mark missed"
                        }</button>
                      </div>
                    </article>
                  `,
                )
                .join("")
            : `<div class="empty-state">No lecture sessions have been created for this room yet.</div>`
        }
      </div>
    </section>
  `;
}

function renderLecturerSessionDetail(workspace, session) {
  return `
    <section class="module-section">
      <div class="section-intro">
        <div>
          <p class="section-kicker">Lecture Session</p>
          <h3>${escapeHtml(session.title)}</h3>
        </div>
        <div class="helper">${escapeHtml(
          [
            currentCourseCode(),
            `Lecture ${session.lecture_number}`,
            session.status,
            session.date_or_week || null,
          ]
            .filter(Boolean)
            .join(" | "),
        )}</div>
      </div>
      <div class="row-actions">
        <button type="button" class="ghost-button" data-action="back-to-session-directory">
          Back to sessions
        </button>
      </div>
      <div class="metric-grid">
        <article class="detail-card metric-card">
          <p class="section-kicker">Status</p>
          <h3>${escapeHtml(session.status)}</h3>
        </article>
        <article class="detail-card metric-card">
          <p class="section-kicker">Attachments</p>
          <h3>${escapeHtml(session.attachment_count || 0)}</h3>
        </article>
        <article class="detail-card metric-card">
          <p class="section-kicker">Indexed Files</p>
          <h3>${escapeHtml(session.indexed_attachment_count || 0)}</h3>
        </article>
      </div>
      <form id="lecture-session-update-form" class="stack" data-session-id="${escapeHtml(session.session_id)}">
        <div class="detail-grid">
          <label>
            <span>Lecture number</span>
            <input type="number" id="session-edit-lecture-number" min="1" max="99" value="${escapeHtml(
              session.lecture_number,
            )}" required>
          </label>
          <label>
            <span>Date or week</span>
            <input type="text" id="session-edit-date-or-week" value="${escapeHtml(
              session.date_or_week || "",
            )}" placeholder="Week 4 or 2026-04-03">
          </label>
        </div>
        <label>
          <span>Topic</span>
          <input type="text" id="session-edit-topic" value="${escapeHtml(session.topic || "")}">
        </label>
        <label>
          <span>Title</span>
          <input type="text" id="session-edit-title" value="${escapeHtml(session.title || "")}">
        </label>
        <label>
          <span>Status</span>
          <select id="session-edit-status">
            <option value="Delivered" ${session.status === "Delivered" ? "selected" : ""}>Delivered</option>
            <option value="Missed" ${session.status === "Missed" ? "selected" : ""}>Missed</option>
            <option value="Make-up" ${session.status === "Make-up" ? "selected" : ""}>Make-up</option>
          </select>
        </label>
        <label>
          <span>Session notes</span>
          <textarea id="session-edit-notes-text" rows="6">${escapeHtml(session.notes_text || "")}</textarea>
        </label>
        <button type="submit" class="primary-button">Save session details</button>
      </form>
      <form id="lecture-session-attachments-form" class="stack" data-session-id="${escapeHtml(session.session_id)}">
        <label>
          <span>Add files to this lecture</span>
          <input type="file" id="session-attachment-files" accept=".pdf,.txt,.md,.csv,.json,.html,.docx" multiple>
        </label>
        <div id="session-attachment-file-list" class="helper">No files selected yet.</div>
        <button type="submit" class="primary-button">Upload attachments</button>
      </form>
      <div class="attachment-list">
        ${renderLecturerAttachmentCards(session.attachments || [])}
      </div>
    </section>
  `;
}

function renderStudentProfileErp(workspace) {
  const profile = workspace.erp_profile || {};
  const fieldRows = [
    ["Registration No:", profile.registration_number || displayRegistrationNumber()],
    ["Name:", profile.name || displayUserName()],
    ["Gender:", profile.gender || "-"],
    ["Nationality:", profile.nationality || state.session?.nationality || "-"],
    ["Birth Date:", profile.birth_date || "-"],
    ["Session:", profile.session || "-"],
    ["Marital Status:", profile.marital_status || "-"],
    ["Arabic Name:", profile.arabic_name || ""],
    ["Religion:", profile.religion || "-"],
    ["Entry Method:", profile.entry_method || "-"],
    ["Entry Year:", profile.entry_year || "-"],
    ["Phone:", profile.phone || "-"],
    ["Email:", profile.email || state.session?.email || "-"],
    ["Hall:", profile.hall || "-"],
    ["Home District:", profile.home_district || "-"],
    ["Intake:", profile.intake || "-"],
  ];
  const half = Math.ceil(fieldRows.length / 2);
  const renderFields = (rows) => rows
    .map(
      ([label, value]) => `
        <div class="erp-profile-row">
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(value)}</span>
        </div>
      `,
    )
    .join("");
  const clearanceRows = (workspace.clearance_history || []).map((entry, index) => [
    index === 0 ? "*" : "o",
    entry.academic_year,
    entry.year,
    entry.semester,
    entry.reg_status,
    entry.retakes,
    entry.status,
    entry.cleared_by,
    entry.date_cleared,
  ]);

  return `
    <section class="erp-page">
      ${renderErpStudentBar(displayUserLine())}
      ${renderLegacyPanel({
        title: "MY PROFILE",
        icon: "&#9636;",
        body: `
          <div class="legacy-tab">Student Profile</div>
          <div class="erp-profile-card">
            <div class="erp-photo-frame">${renderStudentAvatar()}</div>
            <div class="erp-profile-columns">
              <div>${renderFields(fieldRows.slice(0, half))}</div>
              <div>${renderFields(fieldRows.slice(half))}</div>
            </div>
          </div>
          <div class="legacy-section-title">Clearance & Examination Card History</div>
          <div class="legacy-table-wrap">
            ${renderLegacyTable({
              columns: ["#", "Academic Yr", "Year", "Semester", "Reg Status", "Retakes", "Clearance | Exam Card Status", "Cleared By", "Date Cleared"],
              rows: clearanceRows,
              highlightFirst: true,
            })}
          </div>
        `,
      })}
    </section>
  `;
}

function renderRegistrationErp(workspace) {
  const units = workspace.registered_course_units?.length ? workspace.registered_course_units : workspace.courses || [];
  return renderLegacyPanel({
    title: "COURSES & E-CONTENT CENTRE",
    icon: "&#9636;",
    body: `
      <div class="erp-filter-grid">
        <label><span>Academic Year</span><select><option>2025/2026</option></select></label>
        <label><span>Semester</span><select><option>2</option></select></label>
        <label><span>New Course Unit:</span><select><option></option></select></label>
      </div>
      <div class="erp-action-row">
        <button type="button" class="legacy-action legacy-action--danger">&#9745; Click to Complete Registration</button>
        <button type="button" class="legacy-action">&#9745; Register Course</button>
      </div>
      <div class="legacy-table-tools">
        <input type="search" placeholder="Enter text to search...">
      </div>
      <div class="legacy-table-wrap">
        ${renderLegacyTable({
          columns: ["#", "Code", "Course Name", "Credit Units", "Notes & Content", "#"],
          rows: units.map((unit, index) => [
            index === 0 ? "*" : "o",
            unit.course_code,
            unit.title,
            unit.credit_units || "4.0",
            "Y",
            "Delete",
          ]),
          highlightFirst: true,
        })}
      </div>
    `,
  });
}

function renderExamResultsErp(workspace) {
  const rows = workspace.exam_result_rows || [];
  return renderLegacyPanel({
    title: "EXAM RESULTS",
    icon: "&#9636;",
    body: `
      <div class="results-status">
        <strong>RESULTS STATUS: FINAL</strong>
        <span>PRINTING IS STRICTLY PROHIBITED</span>
      </div>
      <div class="result-filter-row">
        <label>Year of Study <select><option>1</option><option>2</option><option>3</option></select></label>
        <label>Semester <select><option>2</option><option>1</option></select></label>
        <strong>Academic Year: <span>2023/2024</span></strong>
      </div>
      <div class="legacy-table-wrap">
        ${renderLegacyTable({
          columns: ["Code", "Course", "Credit Units", "Mark", "Grade", "Grade Pt", "Comment"],
          rows: rows.map((row) => [
            row.code,
            row.course,
            row.credit_units,
            row.mark,
            row.grade,
            row.grade_point,
            row.comment,
          ]),
          highlightFirst: true,
        })}
      </div>
      <div class="gpa-block">
        <div><strong>Year 1 Semester 2 Grade Point Average:</strong><span>4.34</span></div>
        <div><strong>General Cumulative Grade Point Average:</strong><span>4.58</span></div>
        <div><strong>Current Degree Class:</strong><span>FIRST CLASS (HONOURS)</span></div>
        <button type="button" class="legacy-action legacy-action--wide">Submit Complaints...</button>
      </div>
    `,
  });
}

function renderFeesErp(workspace) {
  const finance = workspace.finance || {};
  return renderLegacyPanel({
    title: "FEES INFORMATION",
    icon: "&#9637;",
    body: `
      <div class="legacy-table-wrap">
        ${renderLegacyTable({
          columns: ["#", "Account Item", "Status / Balance"],
          rows: [
            [1, "Tuition Balance", finance.tuition_balance || "-"],
            [2, "Library Clearance", finance.library_status || "-"],
            [3, "Hostel Status", finance.hostel_status || "-"],
            [4, "Registration Clearance", workspace.registration?.clearance || "-"],
          ],
          highlightFirst: true,
        })}
      </div>
    `,
  });
}

function renderTimetableErp(workspace) {
  const entries = workspace.timetable?.entries || [];
  return renderLegacyPanel({
    title: "TIMETABLE INFO",
    icon: "&#9635;",
    body: `
      <form id="timetable-form" class="legacy-form">
        <label>
          <span>Available hours per week</span>
          <input type="number" id="timetable-hours" min="4" max="40" value="${escapeHtml(workspace.timetable?.available_hours_per_week || 12)}">
        </label>
        <label>
          <span>Preferred study times</span>
          <input type="text" id="timetable-preferences" value="${escapeHtml((workspace.timetable?.preferred_times || ["18:30 - 20:30", "06:30 - 08:30"]).join(", "))}">
        </label>
        <button type="submit" class="legacy-action">Generate timetable</button>
      </form>
      <div class="legacy-table-wrap">
        ${renderLegacyTable({
          columns: ["#", "Day", "Time", "Course", "Duration", "Focus"],
          rows: entries.map((entry, index) => [
            index + 1,
            entry.day,
            entry.time,
            entry.course_code,
            `${entry.duration_hours} hr(s)`,
            entry.focus,
          ]),
        })}
      </div>
    `,
  });
}

function renderAnnouncementsErp(workspace) {
  return renderLegacyPanel({
    title: "NOTIFICATIONS",
    icon: "&#9888;",
    body: `
      <div class="notice-list">
        ${(workspace.announcements || []).length
          ? workspace.announcements.map((notice, index) => `
            <article class="notice-row">
              <strong>#${index + 1}</strong>
              <span>${escapeHtml(notice)}</span>
            </article>
          `).join("")
          : `<div class="empty-state">No notifications are available.</div>`}
      </div>
    `,
  });
}

function renderLibraryErp(workspace) {
  const rowsHtml = (workspace.resources || [])
    .map(
      (resource, index) => `
        <tr>
          <td>${escapeHtml(index + 1)}</td>
          <td>${escapeHtml(resource.course_code)}</td>
          <td>${escapeHtml(resource.material_label || resource.title)}</td>
          <td>${escapeHtml(resource.topic || "-")}</td>
          <td>${escapeHtml(resource.week || "-")}</td>
          <td>
            <button type="button" class="legacy-mini-button" data-action="open-resource" data-resource-id="${escapeHtml(resource.resource_id)}">Open</button>
            <button type="button" class="legacy-mini-button" data-action="open-resource-pdf" data-resource-id="${escapeHtml(resource.resource_id)}" data-translate="true">PDF</button>
          </td>
        </tr>
      `,
    )
    .join("");
  return renderLegacyPanel({
    title: "LIBRARY CENTRE",
    icon: "&#9632;",
    body: `
      ${renderDataToolbar()}
      <div class="legacy-table-wrap">
        ${renderLegacyTableRaw({
          columns: ["#", "Code", "Resource", "Topic", "Week", "Details"],
          rowsHtml,
        })}
      </div>
    `,
  });
}

function renderFeedbackErp(workspace) {
  const resources = workspace.resources || [];
  const resourceOptions = fillCourseResourceOptions(resources, state.activeResourceId || "");
  const hasResources = resources.length > 0;
  return renderLegacyPanel({
    title: "FEEDBACK TO LECTURER",
    icon: "&#9993;",
    body: `
      <form id="feedback-form" class="legacy-form">
        <label>
          <span>Course unit</span>
          <select id="feedback-course-code" required>${fillStudentCourseUnitOptions()}</select>
        </label>
        <label>
          <span>Course resource</span>
          <select id="feedback-resource-id" ${hasResources ? "required" : "disabled"}>
            <option value="">${hasResources ? "Select course resource" : "No resources are available for this course"}</option>
            ${resourceOptions}
          </select>
        </label>
        <label><span>Difficulty area</span><input type="text" id="feedback-difficulty" placeholder="Example: ERP workflow mapping" required></label>
        <label><span>Topic</span><input type="text" id="feedback-topic" placeholder="Optional topic"></label>
        <label><span>Comment / question</span><textarea id="feedback-comment" rows="4" required></textarea></label>
        <button type="submit" class="legacy-action">Send feedback</button>
      </form>
      <div class="legacy-table-wrap">
        ${renderLegacyTable({
          columns: ["#", "Course", "Resource", "Difficulty Area", "Comment"],
          rows: (workspace.feedback_history || []).map((entry, index) => [
            index + 1,
            entry.course_code,
            entry.resource_title || "-",
            entry.difficulty_area,
            entry.comment,
          ]),
        })}
      </div>
    `,
  });
}

function renderElearningHero(title) {
  return `
    <section class="elearn-card elearn-hero-card">
      <h2>${escapeHtml(title)}</h2>
    </section>
  `;
}

function renderElearningDashboard(workspace) {
  const notices = workspace.announcements || [];
  return `
    ${renderElearningHero("DIGITAL LEARNING SUPPORT PLATFORM")}
    <div class="session-chip">&#9635; CURRENT STUDY SESSION :: SEMESTER 2, 2025/2026</div>
    <div class="elearn-stat-grid">
      <article class="elearn-stat"><h3>MY STUDY LOAD</h3><strong>${escapeHtml((workspace.registered_course_units || []).length || (workspace.courses || []).length)}</strong><span>Classes Allocated</span><em>&#9632;</em></article>
      <article class="elearn-stat"><h3>COMMUNICATIONS</h3><strong>0</strong><span>Pending Lecturer Chats</span><em>&#9787;</em></article>
      <article class="elearn-stat"><h3>KEY DEADLINES</h3><strong>04 May, 2026</strong><span>Examinations Submission</span><em>&#9635;</em></article>
    </div>
    <section class="elearn-card notices-card">
      <h2>&#128226; NOTICES & ANNOUNCEMENTS</h2>
      <article class="director-message">
        <span class="notice-date">23 February, 2026</span>
        <h3>#236 DIRECTOR'S MESSAGE</h3>
        <p>All students<br>Islamic University In Uganda - Kampala Campus</p>
        <p>Dear students,</p>
        <p>Assalam Alaykum Warahmatullah Wabarakatuh</p>
        ${notices.map((notice) => `<p>${escapeHtml(notice)}</p>`).join("")}
      </article>
    </section>
  `;
}

function renderElearningClassAllocation(workspace) {
  const units = workspace.registered_course_units?.length ? workspace.registered_course_units : workspace.courses || [];
  const rowsHtml = units
    .map(
      (unit, index) => `
        <tr>
          <td><input type="checkbox" aria-label="Select ${escapeHtml(unit.course_code)}"></td>
          <td>${escapeHtml(index + 1)}</td>
          <td>${escapeHtml(unit.course_code)}</td>
          <td>${escapeHtml(unit.title)}</td>
          <td>${escapeHtml(unit.class || unit.year_of_study || "BIT YR 3 [DAY]")}</td>
          <td><span class="hours-pill">${escapeHtml(unit.hours_per_week || 4)}</span></td>
          <td>${escapeHtml(unit.lecturer || "Lecturer")}</td>
          <td><button type="button" class="purple-button" data-action="open-course-room" data-course-code="${escapeHtml((workspace.courses || [])[index]?.course_code || currentCourseCode())}">Enroll/View Class</button></td>
          <td><button type="button" class="purple-button">Inter-Campus</button></td>
        </tr>
      `,
    )
    .join("");
  return `
    <section class="elearn-card">
      <h2>DIGITAL CLASS ALLOCATION</h2>
      <div class="elearn-filter-grid">
        <label><span>Academic Year:</span><select><option>2025/2026</option></select></label>
        <label><span>Semester:</span><select><option>2</option></select></label>
        <label><span>Study System</span><select><option>Semester</option></select></label>
      </div>
    </section>
    <section class="elearn-card">
      <h2>CLASSES</h2>
      ${renderDataToolbar()}
      <div class="legacy-table-wrap">
        ${renderLegacyTableRaw({
          columns: ["", "#", "Code", "Course Name", "Class", "Hours|Week", "Lecturer", "Enrolment", "Inter-Campus"],
          rowsHtml,
        })}
      </div>
    </section>
  `;
}

function renderElearningExaminations(workspace) {
  const quizzes = workspace.quizzes || [];
  const rowsHtml = quizzes
    .map(
      (quiz) => `
        <tr>
          <td><input type="checkbox" aria-label="Select ${escapeHtml(quiz.title)}"></td>
          <td>${escapeHtml(quiz.course_code)}</td>
          <td>${escapeHtml(quiz.title)}</td>
          <td>${escapeHtml(state.session?.year_of_study || "BIT YR 3 [DAY]")}</td>
          <td>${escapeHtml(quiz.generated_at || "-")}</td>
          <td>${escapeHtml(quiz.latest_attempt ? `${quiz.latest_attempt.percentage}%` : "Available")}</td>
          <td><button type="button" class="purple-button" data-action="open-student-quiz" data-quiz-id="${escapeHtml(quiz.quiz_id)}">Details</button></td>
        </tr>
      `,
    )
    .join("");
  return `
    <section class="elearn-card">
      <h2>EXAMINATIONS CENTRE</h2>
      <div class="elearn-filter-grid">
        <label><span>Academic Year:</span><select><option>2025/2026</option></select></label>
        <label><span>Semester:</span><select><option>2</option></select></label>
        <label><span>Study System</span><select><option>Semester</option></select></label>
      </div>
    </section>
    <section class="elearn-card">
      <h2>EXAMINATIONS</h2>
      ${renderDataToolbar()}
      <div class="legacy-table-wrap">
        ${renderLegacyTableRaw({
          columns: ["", "Code", "Course Name", "Candidate Class", "Date & Time", "Status", "Details"],
          rowsHtml,
        })}
      </div>
      ${quizzes.length ? "" : `<div class="legacy-pagination">Showing 0 to 0 of 0 entries <button>Previous</button><button>Next</button></div>`}
    </section>
  `;
}

function renderStudentModule(module) {
  const workspace = state.workspace || {};

  switch (module) {
    case "profile":
      return detailRows([
        { label: "Student ID", value: workspace.student_id || "-" },
        { label: "Program", value: state.session?.program || "-" },
        { label: "Year", value: state.session?.year_of_study || "-" },
        { label: "Study Language", value: languageName(workspace.profile?.preferred_language) },
      ]);
    case "results":
      return (workspace.results || []).length
        ? `<div class="resource-list">${(workspace.results || [])
            .map(
              (result) => `
                <article class="detail-card">
                  <h3>${escapeHtml(result.course_code)}</h3>
                  <div class="helper">${escapeHtml(result.assessment)}</div>
                  <div class="chip">${escapeHtml(result.score)}</div>
                </article>
              `,
            )
            .join("")}</div>`
        : `<div class="empty-state">No assessment results are available.</div>`;
    case "fees_info":
      return detailRows([
        { label: "Tuition Balance", value: workspace.finance?.tuition_balance || "-" },
        { label: "Library", value: workspace.finance?.library_status || "-" },
        { label: "Hostel", value: workspace.finance?.hostel_status || "-" },
      ]);
    case "my_timetable":
      return `
        <form id="timetable-form" class="stack">
          <label>
            <span>Available hours per week</span>
            <input type="number" id="timetable-hours" min="4" max="40" value="${escapeHtml(
              workspace.timetable?.available_hours_per_week || 12,
            )}">
          </label>
          <label>
            <span>Preferred study times</span>
            <input type="text" id="timetable-preferences" value="${escapeHtml(
              (workspace.timetable?.preferred_times || ["18:30 - 20:30", "06:30 - 08:30"]).join(", "),
            )}" placeholder="18:30 - 20:30, 06:30 - 08:30">
          </label>
          <button type="submit" class="primary-button">Generate timetable</button>
        </form>
        <div class="resource-list">
          ${((workspace.timetable?.entries || []).length
            ? workspace.timetable.entries
                .map(
                  (entry) => `
                    <article class="detail-card">
                      <h3>${escapeHtml(entry.day)}</h3>
                      <div class="helper">${escapeHtml(
                        `${entry.time} | ${entry.course_code} | ${entry.duration_hours} hr(s)`,
                      )}</div>
                      <div class="helper">${escapeHtml(entry.focus)}</div>
                    </article>
                  `,
                )
                .join("")
            : `<div class="empty-state">Generate a timetable to see your study sessions.</div>`)}
        </div>
      `;
    case "e_learning_centre":
      return state.activeCourseUnitCode
        ? renderStudentCourseResourceView(workspace)
        : renderStudentCourseUnits(workspace);
    case "study_planner":
      return `
        <form id="study-plan-form" class="stack">
          <label>
            <span>Study hours per week</span>
            <input type="number" id="study-plan-hours" min="4" max="40" value="${escapeHtml(
              workspace.study_plan?.study_hours_per_week || 12,
            )}">
          </label>
          <button type="submit" class="primary-button">Refresh study plan</button>
        </form>
        <div class="helper">${escapeHtml(workspace.study_plan?.summary || "No study plan prepared yet.")}</div>
        <div class="resource-list">
          ${((workspace.study_plan?.recommendations || []).length
            ? workspace.study_plan.recommendations
                .map(
                  (recommendation) => `
                    <article class="detail-card">
                      <h3>${escapeHtml(recommendation.course_code)}</h3>
                      <div class="helper">${escapeHtml(
                        `${recommendation.priority} priority | ${recommendation.recommended_hours} hr(s)`,
                      )}</div>
                      <div class="helper">${escapeHtml(recommendation.reason)}</div>
                      <div class="helper">${escapeHtml(recommendation.next_action)}</div>
                    </article>
                  `,
                )
                .join("")
            : `<div class="empty-state">Generate a study plan to view recommendations.</div>`)}
        </div>
      `;
    case "quiz_centre":
      return state.activeStudentQuizId && currentStudentQuiz()
        ? renderStudentQuizDetail(currentStudentQuiz())
        : renderQuizCentre(workspace.quizzes || []);
    case "my_registration":
      return detailRows([
        { label: "Semester", value: workspace.registration?.semester || "-" },
        { label: "Status", value: workspace.registration?.status || "-" },
        { label: "Clearance", value: workspace.registration?.clearance || "-" },
      ]);
    case "announcements":
      return (workspace.announcements || []).length
        ? `<div class="resource-list">${workspace.announcements
            .map(
              (announcement) => `
                <article class="detail-card">
                  <div class="helper">${escapeHtml(announcement)}</div>
                </article>
              `,
            )
            .join("")}</div>`
        : `<div class="empty-state">No announcements are available.</div>`;
    case "library":
      return renderStudentCourseResourceView(workspace);
    case "feedback_to_lecturer":
      return `
        <form id="feedback-form" class="stack">
          <label>
            <span>Difficulty area</span>
            <input type="text" id="feedback-difficulty" placeholder="Example: ERP workflow mapping" required>
          </label>
          <label>
            <span>Topic</span>
            <input type="text" id="feedback-topic" placeholder="Optional topic">
          </label>
          <label>
            <span>Comment / question</span>
            <textarea id="feedback-comment" rows="4" placeholder="Describe the part you did not understand." required></textarea>
          </label>
          <button type="submit" class="primary-button">Send feedback</button>
        </form>
        <div class="feedback-list">
          ${(workspace.feedback_history || []).length
            ? workspace.feedback_history
                .map(
                  (entry) => `
                    <article class="feedback-card">
                      <h3>${escapeHtml(entry.course_code)}</h3>
                      <div class="helper">${escapeHtml(entry.difficulty_area)}</div>
                      <div class="helper">${escapeHtml(entry.comment)}</div>
                    </article>
                  `,
                )
                .join("")
            : `<div class="empty-state">No feedback has been submitted yet.</div>`}
        </div>
      `;
    default:
      return `<div class="empty-state">This student module is not available yet.</div>`;
  }
}

function renderStudentModule(module) {
  const workspace = state.workspace || {};

  switch (module) {
    case "profile":
      if (state.activeModule === "elearning_profile") {
        const preferredLanguage = workspace.profile?.preferred_language || "";
        return `
          ${renderElearningHero("MY PROFILE")}
          <section class="elearn-card">
            <div class="erp-profile-card erp-profile-card--elearn">
              <div class="erp-photo-frame">${renderStudentAvatar()}</div>
              <div class="erp-profile-columns">
                <div class="erp-profile-row"><strong>Registration No:</strong><span>${escapeHtml(displayRegistrationNumber())}</span></div>
                <div class="erp-profile-row"><strong>Name:</strong><span>${escapeHtml(displayUserName())}</span></div>
                <div class="erp-profile-row"><strong>Program:</strong><span>${escapeHtml(state.session?.program || "-")}</span></div>
                <div class="erp-profile-row"><strong>Campus:</strong><span>${escapeHtml(state.session?.campus || "-")}</span></div>
              </div>
            </div>
            <form id="preferred-language-form" class="legacy-form preferred-language-form">
              <label>
                <span>Preferred Language</span>
                <select id="preferred-language-select">
                  ${fillPreferredLanguageOptions(preferredLanguage)}
                </select>
              </label>
              <div class="chip">Current: ${escapeHtml(languageName(preferredLanguage))}</div>
              <button type="submit" class="primary-button">Save Language</button>
            </form>
          </section>
        `;
      }
      return renderStudentProfileErp(workspace);
    case "results":
      return renderExamResultsErp(workspace);
    case "fees_info":
      return renderFeesErp(workspace);
    case "my_timetable":
      return renderTimetableErp(workspace);
    case "e_learning_centre":
      if (state.activeModule === "elearning_dashboard") {
        return renderElearningDashboard(workspace);
      }
      return state.activeCourseUnitCode
        ? renderStudentCourseResourceView(workspace)
        : renderElearningClassAllocation(workspace);
    case "study_planner":
      return `
        ${renderElearningHero("DIGITAL LEARNING SUPPORT PLATFORM")}
        <section class="elearn-card">
          <h2>USER GUIDE</h2>
          <form id="study-plan-form" class="legacy-form">
            <label>
              <span>Study hours per week</span>
              <input type="number" id="study-plan-hours" min="4" max="40" value="${escapeHtml(workspace.study_plan?.study_hours_per_week || 12)}">
            </label>
            <button type="submit" class="purple-button">Refresh study plan</button>
          </form>
          <p class="helper">${escapeHtml(workspace.study_plan?.summary || "No study plan prepared yet.")}</p>
          <div class="legacy-table-wrap">
            ${renderLegacyTable({
              columns: ["Course", "Priority", "Hours", "Reason", "Next Action"],
              rows: (workspace.study_plan?.recommendations || []).map((recommendation) => [
                recommendation.course_code,
                recommendation.priority,
                recommendation.recommended_hours,
                recommendation.reason,
                recommendation.next_action,
              ]),
            })}
          </div>
        </section>
      `;
    case "quiz_centre":
      return state.activeStudentQuizId && currentStudentQuiz()
        ? renderStudentQuizDetail(currentStudentQuiz())
        : renderElearningExaminations(workspace);
    case "my_registration":
      return renderRegistrationErp(workspace);
    case "announcements":
      return renderAnnouncementsErp(workspace);
    case "library":
      return renderLibraryErp(workspace);
    case "feedback_to_lecturer":
      return renderFeedbackErp(workspace);
    default:
      return `<div class="empty-state">This student module is not available yet.</div>`;
  }
}

function renderLecturerModule(module) {
  const workspace = state.workspace || {};
  switch (module) {
    case "virtual_lecturer_rooms":
      return state.activeLecturerRoomCode
        ? renderLecturerRoomDetail(workspace)
        : renderLecturerRoomDirectory(workspace);
    case "todays_classes":
      return (workspace.today_schedule || []).length
        ? `<div class="resource-list">${workspace.today_schedule
            .map(
              (entry) => `
                <article class="detail-card">
                  <h3>${escapeHtml(entry.time)}</h3>
                  <div class="helper">${escapeHtml(entry.title)}</div>
                  <div class="helper">${escapeHtml(
                    [entry.course_code, entry.location].filter(Boolean).join(" | "),
                  )}</div>
                </article>
              `,
            )
            .join("")}</div>`
        : `<div class="empty-state">No teaching sessions are scheduled today.</div>`;
    case "upload_resources":
      return state.activeLecturerSessionId && currentLectureSession()
        ? renderLecturerSessionDetail(workspace, currentLectureSession())
        : renderLecturerSessionDirectory(workspace);
    case "quiz_generator":
      return `
        <form id="quiz-generator-form" class="stack">
          <label>
            <span>Course Code</span>
            <select id="quiz-course-code" required>
              ${fillLecturerCourseOptions()}
            </select>
          </label>
          <label>
            <span>Topic</span>
            <input type="text" id="quiz-topic" placeholder="Optional topic">
          </label>
          <label>
            <span>Source resource</span>
            <select id="quiz-resource-id">
              <option value="">All indexed resources</option>
              ${(workspace.resources || [])
                .map(
                  (resource) =>
                    `<option value="${escapeHtml(resource.resource_id)}">${escapeHtml(
                      resource.title,
                    )}</option>`,
                )
                .join("")}
            </select>
          </label>
          <label>
            <span>Questions</span>
            <input type="number" id="quiz-question-count" min="2" value="10">
          </label>
          <button type="submit" class="primary-button">Generate quiz</button>
        </form>
      `;
    case "quiz_review":
      return state.activeLecturerQuizId && currentLecturerQuiz()
        ? renderLecturerQuizDetail(currentLecturerQuiz())
        : renderQuizReview(workspace.quizzes || []);
    case "announcements":
      return (workspace.announcements || []).length
        ? `<div class="resource-list">${workspace.announcements
            .map(
              (announcement) => `
                <article class="detail-card">
                  <div class="helper">${escapeHtml(announcement)}</div>
                </article>
              `,
            )
            .join("")}</div>`
        : `<div class="empty-state">No announcements are available.</div>`;
    case "student_feedback":
      return renderLecturerFeedback(workspace.student_feedback || { entries: [], by_topic: [] });
    default:
      return `<div class="empty-state">This lecturer module is not available yet.</div>`;
  }
}

function renderQuizCentre(quizzes) {
  if (!quizzes.length) {
    return `<div class="empty-state">No quizzes are available yet. Ask the lecturer to generate one from uploaded notes.</div>`;
  }

  return `
    <div class="quiz-list">
      ${quizzes
        .map(
          (quiz) => `
            <button
              type="button"
              class="quiz-card quiz-card--interactive"
              data-action="open-student-quiz"
              data-quiz-id="${escapeHtml(quiz.quiz_id)}"
            >
              <div class="quiz-head">
                <div>
                  <h3>${escapeHtml(quiz.title)}</h3>
                  <div class="helper">${escapeHtml(
                    `${quiz.course_code} | ${quiz.topic || "General"} | ${quiz.question_count} question(s)`,
                  )}</div>
                </div>
                <span class="chip">${escapeHtml(
                  quiz.latest_attempt ? `${quiz.latest_attempt.percentage}%` : "New",
                )}</span>
              </div>
              <div class="helper">${escapeHtml(
                quiz.latest_attempt
                  ? `Latest attempt: ${quiz.latest_attempt.percentage}%`
                  : "Not attempted yet. Open this tile to start the quiz.",
              )}</div>
              <div class="helper">${escapeHtml(
                quiz.questions?.[0]?.prompt
                  ? `Preview: ${quiz.questions[0].prompt}`
                  : "Questions are ready for this quiz.",
              )}</div>
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderStudentQuizDetail(quiz) {
  return `
    <section class="module-section">
      <div class="section-intro">
        <div>
          <p class="section-kicker">Quiz Detail</p>
          <h3>${escapeHtml(quiz.title)}</h3>
        </div>
        <div class="helper">${escapeHtml(
          `${quiz.course_code} | ${quiz.topic || "General"} | ${quiz.question_count} question(s)`,
        )}</div>
      </div>
      <div class="row-actions">
        <button type="button" class="ghost-button" data-action="back-to-student-quizzes">
          Back to quizzes
        </button>
      </div>
      <form class="quiz-attempt-form stack" data-quiz-id="${escapeHtml(quiz.quiz_id)}">
        ${quiz.questions
          .map(
            (question, questionIndex) => `
              <div class="detail-card">
                <div class="helper"><strong>Q${questionIndex + 1}.</strong> ${escapeHtml(
                  question.prompt,
                )}</div>
                <div class="quiz-options">
                  ${question.options
                    .map(
                      (option, optionIndex) => `
                        <label class="option-row">
                          <input type="radio" name="${escapeHtml(
                            `quiz-${quiz.quiz_id}-${question.question_id}`,
                          )}" value="${optionIndex}">
                          <span>${escapeHtml(option)}</span>
                        </label>
                      `,
                    )
                    .join("")}
                </div>
              </div>
            `,
          )
          .join("")}
        <button type="submit" class="primary-button">Submit quiz</button>
      </form>
    </section>
  `;
}

function renderQuizReview(quizzes) {
  if (!quizzes.length) {
    return `<div class="empty-state">No prepared quizzes are available for review.</div>`;
  }

  return `
    <div class="quiz-list">
      ${quizzes
        .map(
          (quiz) => `
            <button
              type="button"
              class="quiz-card quiz-card--interactive"
              data-action="open-lecturer-quiz"
              data-quiz-id="${escapeHtml(quiz.quiz_id)}"
            >
              <div class="quiz-head">
                <div>
                  <h3>${escapeHtml(quiz.title)}</h3>
                  <div class="helper">${escapeHtml(
                    `${quiz.course_code} | ${quiz.topic || "General"} | ${quiz.question_count} question(s)`,
                  )}</div>
                </div>
                <span class="chip">${escapeHtml(`${quiz.attempt_count || 0} attempt(s)`)}</span>
              </div>
              <div class="helper">${escapeHtml(
                quiz.participant_count
                  ? `${quiz.pass_count} passed | ${quiz.fail_count} failed | ${quiz.participant_count} student(s)`
                  : "No student attempts recorded yet.",
              )}</div>
              <div class="helper">Best student score: ${escapeHtml(
                quiz.best_score != null ? `${quiz.best_score}%` : "No attempt yet",
              )}</div>
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderLecturerQuizDetail(quiz) {
  return `
    <section class="module-section">
      <div class="section-intro">
        <div>
          <p class="section-kicker">Quiz Detail</p>
          <h3>${escapeHtml(quiz.title)}</h3>
        </div>
        <div class="helper">${escapeHtml(
          [quiz.course_code, quiz.topic || "General", `${quiz.question_count} question(s)`].join(" | "),
        )}</div>
      </div>
      <div class="row-actions">
        <button type="button" class="ghost-button" data-action="back-to-quiz-review">
          Back to quizzes
        </button>
      </div>
      <div class="metric-grid">
        <article class="detail-card metric-card">
          <p class="section-kicker">Participants</p>
          <h3>${escapeHtml(quiz.participant_count || 0)}</h3>
        </article>
        <article class="detail-card metric-card">
          <p class="section-kicker">Passed</p>
          <h3>${escapeHtml(quiz.pass_count || 0)}</h3>
        </article>
        <article class="detail-card metric-card">
          <p class="section-kicker">Failed</p>
          <h3>${escapeHtml(quiz.fail_count || 0)}</h3>
        </article>
        <article class="detail-card metric-card">
          <p class="section-kicker">Attempts</p>
          <h3>${escapeHtml(quiz.attempt_count || 0)}</h3>
        </article>
        <article class="detail-card metric-card">
          <p class="section-kicker">Average Score</p>
          <h3>${escapeHtml(quiz.average_score != null ? `${quiz.average_score}%` : "No attempts")}</h3>
        </article>
        <article class="detail-card metric-card">
          <p class="section-kicker">Best Score</p>
          <h3>${escapeHtml(quiz.best_score != null ? `${quiz.best_score}%` : "No attempts")}</h3>
        </article>
      </div>
      <section class="module-section">
        <div class="section-intro">
          <div>
            <p class="section-kicker">Student Results</p>
            <h3>Latest result per student</h3>
          </div>
          <div class="helper">Pass mark: ${escapeHtml(`${quiz.pass_mark || 50}%`)}</div>
        </div>
        <div class="resource-list">
          ${
            quiz.participant_results?.length
              ? quiz.participant_results
                  .map(
                    (result) => `
                      <article class="detail-card">
                        <h3>${escapeHtml(result.student_name)}</h3>
                        <div class="helper">${escapeHtml(
                          `${result.status} | ${result.score}/${result.total_questions} | ${result.percentage}%`,
                        )}</div>
                        <div class="helper">${escapeHtml(result.submitted_at)}</div>
                      </article>
                    `,
                  )
                  .join("")
              : `<div class="empty-state">No student has attempted this quiz yet.</div>`
          }
        </div>
      </section>
      <section class="module-section">
        <div class="section-intro">
          <div>
            <p class="section-kicker">Questions</p>
            <h3>Quiz content</h3>
          </div>
        </div>
        <div class="resource-list">
          ${(quiz.questions || [])
            .map(
              (question, index) => `
                <article class="detail-card">
                  <h3>${escapeHtml(`Question ${index + 1}`)}</h3>
                  <div class="helper">${escapeHtml(question.prompt)}</div>
                  <div class="helper">${escapeHtml(
                    `Correct answer: ${question.options?.[question.answer_index] || "Not set"}`,
                  )}</div>
                </article>
              `,
            )
            .join("")}
        </div>
      </section>
    </section>
  `;
}

function renderLecturerFeedback(payload) {
  return `
    <div class="resource-list">
      ${payload.by_topic?.length
        ? payload.by_topic
            .map(
              (topic) => `
                <article class="detail-card">
                  <h3>${escapeHtml(topic.topic)}</h3>
                  <div class="helper">${escapeHtml(`${topic.count} note(s)`)}</div>
                  <div class="helper">${escapeHtml(topic.latest_comment || "")}</div>
                </article>
              `,
            )
            .join("")
        : `<div class="empty-state">No student feedback has been submitted yet.</div>`}
      ${payload.entries?.length
        ? payload.entries
            .map(
              (entry) => `
                <article class="feedback-card">
                  <h3>${escapeHtml(entry.student_name)}</h3>
                  <div class="helper">${escapeHtml(
                    [entry.course_code, entry.topic || entry.difficulty_area].filter(Boolean).join(" | "),
                  )}</div>
                  <div class="helper">${escapeHtml(`Resource: ${entry.resource_title || "No resource selected"}`)}</div>
                  <div class="helper">${escapeHtml(entry.comment)}</div>
                </article>
              `,
            )
            .join("")
        : ""}
    </div>
  `;
}

function renderChatDrawer() {
  if (!state.session) {
    document.getElementById("chat-drawer").classList.add("hidden");
    return;
  }

  const context = currentChatContext();
  document.getElementById("chat-drawer").classList.toggle("hidden", !state.chatOpen);
  setHtml(
    "chat-drawer",
    `
      <div class="chat-header">
        <div>
          <h3>Course Help</h3>
          <div class="helper">${escapeHtml(context.label)}</div>
        </div>
        <button type="button" class="chat-close" data-action="close-chat">x</button>
      </div>
      <form id="chat-form" class="stack">
        <label>
          <span>Question</span>
          <textarea id="chat-question" rows="4" placeholder="Ask about the current course or resource." required></textarea>
        </label>
        <button type="submit" class="primary-button">Ask</button>
      </form>
      ${
        state.chatResult
          ? `
            <div class="chat-thread">
              <div class="chat-bubble">${escapeHtml(state.chatResult.answer || "")}</div>
              <div class="chat-bubble">${escapeHtml(state.chatResult.citations || "No citations returned.")}</div>
              ${
                state.chatResult.translation
                  ? `<div class="chat-bubble">${escapeHtml(state.chatResult.translation)}</div>`
                  : ""
              }
            </div>
          `
          : ""
      }
    `,
  );
}

function renderAuthenticatedApp() {
  showAuthenticated();
  const shell = activeShell();
  const stage = document.getElementById("app-stage");
  const phoneShell = document.querySelector(".phone-shell");
  stage.dataset.shell = shell;
  stage.classList.toggle("is-elearning", shell === "elearning");
  stage.classList.toggle("is-academica", shell === "academica");
  phoneShell?.classList.toggle("phone-shell--elearning", shell === "elearning");
  phoneShell?.classList.toggle("phone-shell--academica", shell === "academica");
  setHtml("app-header", renderHeader());
  setHtml("app-main", state.activeModule ? renderModule() : renderHome());
  renderChatDrawer();
}

async function loadLanguages() {
  state.languages = await requestJson("/languages");
}

function checkUpcomingLectures() {
  const schedule = state.workspace?.today_schedule || [];
  if (!schedule.length) return;

  const now = new Date();
  for (const entry of schedule) {
    if (!entry.time) continue;
    const [h, m] = entry.time.split(":").map(Number);
    if (isNaN(h) || isNaN(m)) continue;

    const lectureTime = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m, 0, 0);
    const minutesUntil = (lectureTime - now) / 60000;
    const key = `${entry.course_code}_${entry.time}`;

    if (minutesUntil >= 28 && minutesUntil <= 32 && !state.notificationsFired.has(key)) {
      state.notificationsFired.add(key);
      const body = `${entry.title}${entry.location ? " — " + entry.location : ""} starts at ${entry.time}`;
      showAppMessage(`Reminder: ${body}`, "success");
      if (Notification.permission === "granted") {
        new Notification("Upcoming Lecture — 30 Minutes", { body, icon: "/favicon.ico" });
      }
    }
  }
}

async function requestLecturerNotificationPermission() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    await Notification.requestPermission();
  }
}

async function loginWithCredentials(username, password) {
  const payload = await requestJson("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  state.session = payload.user;
  state.workspace = payload.workspace;
  state.activeModule = null;
  state.activeCourseUnitCode = null;
  state.activeStudentLectureSessionId = null;
  state.activeStudentQuizId = null;
  state.activeLecturerRoomCode = null;
  state.activeLecturerQuizId = null;
  state.activeLecturerSessionId = null;
  state.showLectureSessionComposer = false;
  state.activeResourceId = null;
  state.chatOpen = false;
  state.chatResult = null;
  state.notificationsFired = new Set();
  if (state.notificationCheckInterval) {
    clearInterval(state.notificationCheckInterval);
  }
  if (payload.user?.role === "lecturer") {
    requestLecturerNotificationPermission();
    checkUpcomingLectures();
    state.notificationCheckInterval = setInterval(checkUpcomingLectures, 60000);
  }
  hideAppMessage();
  renderAuthenticatedApp();
}

async function loadCurrentWorkspace(courseCode = currentCourseCode()) {
  if (!state.session) {
    return;
  }

  let workspace;
  if (state.session.role === "lecturer") {
    const suffix = courseCode ? `?course_code=${encodeURIComponent(courseCode)}` : "";
    workspace = await requestJson(`/lecturer/${encodeURIComponent(state.session.lecturer_id)}${suffix}`);
  } else {
    const suffix = courseCode ? `?course_code=${encodeURIComponent(courseCode)}` : "";
    workspace = await requestJson(`/student/${encodeURIComponent(state.session.student_id)}${suffix}`);
  }
  state.workspace = workspace;
  if (state.activeResourceId) {
    const stillAvailable = (workspace.resources || []).some(
      (resource) => resource.resource_id === state.activeResourceId,
    );
    if (!stillAvailable) {
      state.activeResourceId = null;
    }
  }
  if (state.activeStudentLectureSessionId) {
    const stillAvailable = (workspace.lecture_sessions || []).some(
      (session) => session.session_id === state.activeStudentLectureSessionId,
    );
    if (!stillAvailable) {
      state.activeStudentLectureSessionId = null;
    }
  }
  if (state.activeStudentQuizId) {
    const stillAvailable = (workspace.quizzes || []).some(
      (quiz) => quiz.quiz_id === state.activeStudentQuizId,
    );
    if (!stillAvailable) {
      state.activeStudentQuizId = null;
    }
  }
  if (state.activeLecturerQuizId) {
    const stillAvailable = (workspace.quizzes || []).some(
      (quiz) => quiz.quiz_id === state.activeLecturerQuizId,
    );
    if (!stillAvailable) {
      state.activeLecturerQuizId = null;
    }
  }
  if (state.activeLecturerSessionId) {
    const stillAvailable = (workspace.lecture_sessions || []).some(
      (session) => session.session_id === state.activeLecturerSessionId,
    );
    if (!stillAvailable) {
      state.activeLecturerSessionId = null;
    }
  }
  renderAuthenticatedApp();
}

function logout() {
  state.session = null;
  state.workspace = null;
  state.activeModule = null;
  state.activeCourseUnitCode = null;
  state.activeStudentLectureSessionId = null;
  state.activeStudentQuizId = null;
  state.activeLecturerRoomCode = null;
  state.activeLecturerQuizId = null;
  state.activeLecturerSessionId = null;
  state.showLectureSessionComposer = false;
  state.activeResourceId = null;
  state.chatOpen = false;
  state.chatResult = null;
  state.resourceTranslations = {};
  state.notificationsFired = new Set();
  if (state.notificationCheckInterval) {
    clearInterval(state.notificationCheckInterval);
    state.notificationCheckInterval = null;
  }
  document.getElementById("login-form").reset();
  document.getElementById("forgot-form").reset();
  hideAuthMessage("login-feedback");
  hideAuthMessage("forgot-feedback");
  document.getElementById("forgot-panel").classList.add("hidden");
  showLoggedOut();
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  hideAuthMessage("login-feedback");
  try {
    await loginWithCredentials(
      document.getElementById("login-username").value.trim(),
      document.getElementById("login-password").value,
    );
  } catch (error) {
    showAuthMessage("login-feedback", error.message, "error");
  }
}

async function handleForgotSubmit(event) {
  event.preventDefault();
  hideAuthMessage("forgot-feedback");
  try {
    const result = await requestJson("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ username: document.getElementById("forgot-username").value.trim() }),
    });
    showAuthMessage(
      "forgot-feedback",
      `${result.message} Destination: ${result.destination}.`,
      "success",
    );
  } catch (error) {
    showAuthMessage("forgot-feedback", error.message, "error");
  }
}

async function handleTimestepSubmit(event) {
  event.preventDefault();
  try {
    const preferredTimes = document
      .getElementById("timetable-preferences")
      .value.split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    await requestJson("/student/timetables/generate", {
      method: "POST",
      body: JSON.stringify({
        student_id: state.session.student_id,
        available_hours_per_week: Number(document.getElementById("timetable-hours").value || 12),
        preferred_times: preferredTimes,
      }),
    });
    showAppMessage("Timetable prepared for the selected student.", "success");
    await loadCurrentWorkspace();
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleStudyPlanSubmit(event) {
  event.preventDefault();
  try {
    await requestJson("/student/study-plans/generate", {
      method: "POST",
      body: JSON.stringify({
        student_id: state.session.student_id,
        study_hours_per_week: Number(document.getElementById("study-plan-hours").value || 12),
      }),
    });
    showAppMessage("Study plan refreshed.", "success");
    await loadCurrentWorkspace();
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleFeedbackSubmit(event) {
  event.preventDefault();
  const courseCode = document.getElementById("feedback-course-code")?.value.trim() || currentCourseCode();
  const resourceId = document.getElementById("feedback-resource-id")?.value.trim() || null;
  try {
    await requestJson("/student/feedback", {
      method: "POST",
      body: JSON.stringify({
        student_id: state.session.student_id,
        course_code: courseCode,
        difficulty_area: document.getElementById("feedback-difficulty").value.trim(),
        topic: document.getElementById("feedback-topic").value.trim() || null,
        comment: document.getElementById("feedback-comment").value.trim(),
        resource_id: resourceId,
      }),
    });
    showAppMessage("Feedback sent to the lecturer.", "success");
    state.activeResourceId = resourceId;
    await loadCurrentWorkspace(courseCode);
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handlePreferredLanguageSubmit(event) {
  event.preventDefault();
  try {
    await requestJson("/student/profile/language", {
      method: "POST",
      body: JSON.stringify({
        student_id: state.session.student_id,
        preferred_language: document.getElementById("preferred-language-select").value || null,
      }),
    });
    showAppMessage("Preferred language saved.", "success");
    await loadCurrentWorkspace();
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function uploadFilesToLectureSession(sessionId, files) {
  if (!files.length) {
    return null;
  }

  const formData = new FormData();
  formData.append("lecturer_id", state.session.lecturer_id);
  for (const file of files) {
    formData.append("files", file);
  }
  return requestJson(`/lecturer/sessions/${encodeURIComponent(sessionId)}/attachments`, {
    method: "POST",
    body: formData,
  });
}

function renderPendingFileList(inputElement, targetId) {
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  const files = Array.from(inputElement?.files || []);
  target.textContent = files.length
    ? files.map((file) => file.name).join(", ")
    : "No files selected yet.";
}

function buildLectureSessionTitle(lectureNumber, topic) {
  const normalizedNumber = String(lectureNumber || "").trim() || "?";
  const normalizedTopic = String(topic || "").trim();
  return normalizedTopic ? `Lecture ${normalizedNumber} - ${normalizedTopic}` : `Lecture ${normalizedNumber}`;
}

function syncLectureSessionComposerTitle() {
  const titleInput = document.getElementById("session-title");
  const lectureNumberInput = document.getElementById("session-lecture-number");
  const topicInput = document.getElementById("session-topic");
  if (!titleInput || !lectureNumberInput || !topicInput || titleInput.dataset.manual === "true") {
    return;
  }
  titleInput.value = buildLectureSessionTitle(lectureNumberInput.value, topicInput.value);
}

async function handleLectureSessionCreateSubmit(event) {
  event.preventDefault();
  try {
    const payload = {
      lecturer_id: state.session.lecturer_id,
      course_code: currentCourseCode(),
      lecture_number: Number(document.getElementById("session-lecture-number").value || 1),
      title: document.getElementById("session-title").value.trim() || null,
      topic: document.getElementById("session-topic").value.trim() || null,
      status: document.getElementById("session-status").value,
      date_or_week: document.getElementById("session-date-or-week").value.trim() || null,
      notes_text: document.getElementById("session-notes-text").value.trim() || null,
    };
    const createdSession = await requestJson(
      `/lecturer/${encodeURIComponent(state.session.lecturer_id)}/rooms/${encodeURIComponent(currentCourseCode())}/sessions`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
    const files = Array.from(document.getElementById("session-create-files").files || []);
    await uploadFilesToLectureSession(createdSession.session_id, files);
    state.activeLecturerSessionId = createdSession.session_id;
    state.showLectureSessionComposer = false;
    showAppMessage(`Lecture ${createdSession.lecture_number} saved for ${currentCourseCode()}.`, "success");
    await loadCurrentWorkspace(currentCourseCode());
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleLectureSessionUpdateSubmit(event) {
  event.preventDefault();
  const sessionId = event.target.dataset.sessionId;
  try {
    await requestJson(`/lecturer/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        lecturer_id: state.session.lecturer_id,
        lecture_number: Number(document.getElementById("session-edit-lecture-number").value || 1),
        title: document.getElementById("session-edit-title").value.trim() || null,
        topic: document.getElementById("session-edit-topic").value.trim() || null,
        status: document.getElementById("session-edit-status").value,
        date_or_week: document.getElementById("session-edit-date-or-week").value.trim() || null,
        notes_text: document.getElementById("session-edit-notes-text").value.trim() || null,
      }),
    });
    const files = Array.from(document.getElementById("session-attachment-files")?.files || []);
    await uploadFilesToLectureSession(sessionId, files);
    showAppMessage(
      files.length
        ? `Lecture session details updated and ${files.length} attachment(s) uploaded.`
        : "Lecture session details updated.",
      "success",
    );
    await loadCurrentWorkspace(currentCourseCode());
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleLectureSessionAttachmentsSubmit(event) {
  event.preventDefault();
  const sessionId = event.target.dataset.sessionId;
  try {
    const files = Array.from(document.getElementById("session-attachment-files").files || []);
    if (!files.length) {
      throw new Error("Choose at least one file before uploading attachments.");
    }
    await uploadFilesToLectureSession(sessionId, files);
    showAppMessage("Attachments uploaded to the lecture session.", "success");
    await loadCurrentWorkspace(currentCourseCode());
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleLectureSessionStatusChange(sessionId, status) {
  try {
    await requestJson(`/lecturer/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        lecturer_id: state.session.lecturer_id,
        status,
      }),
    });
    showAppMessage(`Lecture session marked ${status}.`, "success");
    await loadCurrentWorkspace(currentCourseCode());
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleQuizGeneratorSubmit(event) {
  event.preventDefault();
  try {
    const courseCode = document.getElementById("quiz-course-code").value.trim();
    await requestJson("/lecturer/quizzes/generate", {
      method: "POST",
      body: JSON.stringify({
        lecturer_id: state.session.lecturer_id,
        course_code: courseCode,
        topic: document.getElementById("quiz-topic").value.trim() || null,
        resource_id: document.getElementById("quiz-resource-id").value || null,
        question_count: Number(document.getElementById("quiz-question-count").value || 3),
      }),
    });
    showAppMessage("Quiz prepared from the selected lecturer notes.", "success");
    state.activeModule = "quiz_review";
    state.activeLecturerQuizId = null;
    await loadCurrentWorkspace(courseCode.toUpperCase());
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleQuizAttemptSubmit(event) {
  event.preventDefault();
  const form = event.target;
  const quizId = form.dataset.quizId;
  const answers = [];
  for (const questionBlock of form.querySelectorAll(".detail-card")) {
    const selected = questionBlock.querySelector("input[type='radio']:checked");
    answers.push(selected ? Number(selected.value) : -1);
  }

  try {
    const result = await requestJson(`/student/quizzes/${encodeURIComponent(quizId)}/attempt`, {
      method: "POST",
      body: JSON.stringify({
        student_id: state.session.student_id,
        answers,
      }),
    });
    showAppMessage(
      `Quiz submitted. Score: ${result.attempt.score}/${result.attempt.total_questions}.`,
      "success",
    );
    await loadCurrentWorkspace();
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleResourceTranslationSubmit(event) {
  event.preventDefault();
  const resource = currentResource();
  if (!resource) {
    return;
  }

  try {
    const result = await requestJson("/student/resources/translate", {
      method: "POST",
      body: JSON.stringify({
        student_id: state.session.student_id,
        resource_id: resource.resource_id,
        target_language: document.getElementById("resource-translation-language").value || null,
        bilingual: true,
      }),
    });
    state.resourceTranslations[resource.resource_id] = result.translation.translated_text;
    showAppMessage("Resource translated successfully.", "success");
    renderAuthenticatedApp();
  } catch (error) {
    showAppMessage(error.message, "error");
  }
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const context = currentChatContext();
  try {
    const result = await requestJson("/student/chat", {
      method: "POST",
      body: JSON.stringify({
        student_id: state.session.role === "student" ? state.session.student_id : null,
        course_code: context.courseCode,
        resource_id: context.resourceId,
        topic: context.topic,
        question: document.getElementById("chat-question").value.trim(),
        translate_response: state.session.role === "student",
        bilingual: true,
      }),
    });
    state.chatResult = {
      answer: result.answer_text || "No answer returned.",
      citations: (result.citations || []).map((citation) => citation.title).join(", ") || "No citations returned.",
      translation: result.translation ? result.translation.translated_text : "",
    };
    renderChatDrawer();
  } catch (error) {
    state.chatResult = {
      answer: "Chat failed.",
      citations: error.message,
      translation: "",
    };
    renderChatDrawer();
  }
}

async function handleCourseChange(event) {
  const selectedCourse = event.target.value;
  state.activeResourceId = null;
  state.activeStudentLectureSessionId = null;
  if (event.target.id === "student-course-unit-select" && state.session?.role === "student") {
    state.activeCourseUnitCode = selectedCourse;
  } else if (event.target.id === "feedback-course-code" && state.session?.role === "student") {
    state.activeCourseUnitCode = null;
  } else if (event.target.id === "quiz-course-code" && state.session?.role === "lecturer") {
    state.activeLecturerRoomCode = selectedCourse;
    state.activeLecturerQuizId = null;
    state.activeLecturerSessionId = null;
  }
  await loadCurrentWorkspace(selectedCourse);
}

function handleGlobalClick(event) {
  const moduleButton = event.target.closest("[data-module]");
  if (moduleButton) {
    hideAppMessage();
    state.activeModule = moduleButton.dataset.module;
    if (state.activeModule !== "e_learning_centre" && state.activeModule !== "library") {
      state.activeCourseUnitCode = null;
      state.activeStudentLectureSessionId = null;
    } else if (state.activeModule === "e_learning_centre") {
      state.activeCourseUnitCode = null;
      state.activeStudentLectureSessionId = null;
    }
    if (state.activeModule !== "quiz_centre") {
      state.activeStudentQuizId = null;
    }
    state.activeLecturerRoomCode = null;
    state.activeLecturerQuizId = null;
    state.activeLecturerSessionId = null;
    state.showLectureSessionComposer = false;
    state.activeResourceId = null;
    renderAuthenticatedApp();
    return;
  }

  const actionButton = event.target.closest("[data-action]");
  if (!actionButton) {
    return;
  }

  const action = actionButton.dataset.action;
  if (action === "logout") {
    logout();
  } else if (action === "go-home") {
    hideAppMessage();
    state.activeModule = null;
    state.activeCourseUnitCode = null;
    state.activeStudentLectureSessionId = null;
    state.activeStudentQuizId = null;
    state.activeLecturerRoomCode = null;
    state.activeLecturerQuizId = null;
    state.activeLecturerSessionId = null;
    state.showLectureSessionComposer = false;
    state.activeResourceId = null;
    renderAuthenticatedApp();
  } else if (action === "open-course-room") {
    hideAppMessage();
    state.activeModule = "e_learning_centre";
    state.activeResourceId = null;
    state.activeCourseUnitCode = actionButton.dataset.courseCode || null;
    state.activeStudentLectureSessionId = null;
    loadCurrentWorkspace(actionButton.dataset.courseCode).catch((error) =>
      showAppMessage(error.message, "error"),
    );
  } else if (action === "open-student-lecture-session") {
    hideAppMessage();
    state.activeStudentLectureSessionId = actionButton.dataset.sessionId || null;
    state.activeResourceId = null;
    renderAuthenticatedApp();
  } else if (action === "open-student-quiz") {
    hideAppMessage();
    state.activeModule = "quiz_centre";
    state.activeStudentQuizId = actionButton.dataset.quizId || null;
    renderAuthenticatedApp();
  } else if (action === "back-to-student-quizzes") {
    hideAppMessage();
    state.activeStudentQuizId = null;
    renderAuthenticatedApp();
  } else if (action === "open-lecturer-room") {
    hideAppMessage();
    const courseCode = actionButton.dataset.courseCode || currentCourseCode() || null;
    state.activeModule = "virtual_lecturer_rooms";
    state.activeResourceId = null;
    state.activeLecturerRoomCode = courseCode;
    state.activeLecturerSessionId = null;
    state.showLectureSessionComposer = false;
    loadCurrentWorkspace(courseCode).catch((error) =>
      showAppMessage(error.message, "error"),
    );
  } else if (action === "open-session-manager") {
    hideAppMessage();
    state.activeModule = "upload_resources";
    state.activeLecturerSessionId = null;
    state.showLectureSessionComposer = false;
    renderAuthenticatedApp();
  } else if (action === "select-upload-room") {
    hideAppMessage();
    const courseCode = actionButton.dataset.courseCode || null;
    state.activeModule = "upload_resources";
    state.activeResourceId = null;
    state.activeLecturerSessionId = null;
    state.showLectureSessionComposer = false;
    state.activeLecturerRoomCode = courseCode;
    loadCurrentWorkspace(courseCode).catch((error) =>
      showAppMessage(error.message, "error"),
    );
  } else if (action === "back-to-course-units") {
    hideAppMessage();
    state.activeModule = "e_learning_centre";
    state.activeCourseUnitCode = null;
    state.activeStudentLectureSessionId = null;
    state.activeResourceId = null;
    renderAuthenticatedApp();
  } else if (action === "back-to-lecture-directory") {
    hideAppMessage();
    state.activeStudentLectureSessionId = null;
    state.activeResourceId = null;
    renderAuthenticatedApp();
  } else if (action === "back-to-lecturer-rooms") {
    hideAppMessage();
    state.activeLecturerRoomCode = null;
    state.activeLecturerSessionId = null;
    state.showLectureSessionComposer = false;
    state.activeResourceId = null;
    renderAuthenticatedApp();
  } else if (action === "show-lecture-session-composer") {
    hideAppMessage();
    state.activeLecturerSessionId = null;
    state.showLectureSessionComposer = true;
    renderAuthenticatedApp();
  } else if (action === "cancel-lecture-session-composer") {
    hideAppMessage();
    state.showLectureSessionComposer = false;
    renderAuthenticatedApp();
  } else if (
    action === "open-lecture-session" ||
    action === "edit-lecture-session" ||
    action === "add-files-lecture-session"
  ) {
    hideAppMessage();
    state.activeLecturerSessionId = actionButton.dataset.sessionId || null;
    state.showLectureSessionComposer = false;
    renderAuthenticatedApp();
  } else if (action === "set-lecture-session-status") {
    hideAppMessage();
    handleLectureSessionStatusChange(
      actionButton.dataset.sessionId || "",
      actionButton.dataset.status || "Delivered",
    ).catch((error) => showAppMessage(error.message, "error"));
  } else if (action === "back-to-session-directory") {
    hideAppMessage();
    state.activeLecturerSessionId = null;
    state.showLectureSessionComposer = false;
    renderAuthenticatedApp();
  } else if (action === "open-lecturer-quiz") {
    hideAppMessage();
    state.activeLecturerQuizId = actionButton.dataset.quizId || null;
    renderAuthenticatedApp();
  } else if (action === "back-to-quiz-review") {
    hideAppMessage();
    state.activeLecturerQuizId = null;
    renderAuthenticatedApp();
  } else if (action === "open-resource") {
    state.activeResourceId = actionButton.dataset.resourceId || null;
    if (state.activeModule !== "e_learning_centre" && state.activeModule !== "library") {
      state.activeModule = "library";
    }
    renderAuthenticatedApp();
  } else if (action === "open-resource-pdf") {
    try {
      openResourcePdf(
        actionButton.dataset.resourceId || "",
        actionButton.dataset.translate !== "false",
      );
    } catch (error) {
      showAppMessage(error.message, "error");
    }
  } else if (action === "close-chat") {
    state.chatOpen = false;
    renderChatDrawer();
  }
}

function bindStaticEvents() {
  document.getElementById("login-form").addEventListener("submit", handleLoginSubmit);
  document.getElementById("forgot-form").addEventListener("submit", handleForgotSubmit);
  document.getElementById("toggle-forgot-password").addEventListener("click", () => {
    document.getElementById("forgot-panel").classList.toggle("hidden");
    document.getElementById("forgot-username").value =
      document.getElementById("login-username").value.trim();
  });
  document.getElementById("cancel-forgot-password").addEventListener("click", () => {
    document.getElementById("forgot-panel").classList.add("hidden");
  });
  document.getElementById("chat-fab").addEventListener("click", () => {
    state.chatOpen = !state.chatOpen;
    renderChatDrawer();
  });
  document.addEventListener("click", handleGlobalClick);
  document.addEventListener("change", (event) => {
    if (event.target.id === "student-course-unit-select") {
      handleCourseChange(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "feedback-course-code") {
      handleCourseChange(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "feedback-resource-id") {
      state.activeResourceId = event.target.value || null;
    } else if (event.target.id === "quiz-course-code") {
      handleCourseChange(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "session-create-files") {
      renderPendingFileList(event.target, "session-create-file-list");
    } else if (event.target.id === "session-attachment-files") {
      renderPendingFileList(event.target, "session-attachment-file-list");
    }
  });
  document.addEventListener("input", (event) => {
    if (event.target.id === "session-title") {
      event.target.dataset.manual = event.target.value.trim() ? "true" : "false";
      if (!event.target.value.trim()) {
        syncLectureSessionComposerTitle();
      }
    } else if (event.target.id === "session-lecture-number" || event.target.id === "session-topic") {
      syncLectureSessionComposerTitle();
    }
  });
  document.addEventListener("submit", (event) => {
    if (event.target.id === "login-form" || event.target.id === "forgot-form") {
      return;
    }
    if (event.target.id === "timetable-form") {
      handleTimestepSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "study-plan-form") {
      handleStudyPlanSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "feedback-form") {
      handleFeedbackSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "preferred-language-form") {
      handlePreferredLanguageSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "lecture-session-create-form") {
      handleLectureSessionCreateSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "lecture-session-update-form") {
      handleLectureSessionUpdateSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "lecture-session-attachments-form") {
      handleLectureSessionAttachmentsSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "quiz-generator-form") {
      handleQuizGeneratorSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.classList.contains("quiz-attempt-form")) {
      handleQuizAttemptSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "resource-translation-form") {
      handleResourceTranslationSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    } else if (event.target.id === "chat-form") {
      handleChatSubmit(event).catch((error) => showAppMessage(error.message, "error"));
    }
  });
}

async function boot() {
  bindStaticEvents();
  showLoggedOut();
  await loadLanguages();
}

boot().catch((error) => {
  showAuthMessage("login-feedback", error.message, "error");
});
