function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
}

async function loadHealth() {
  try {
    const health = await requestJson("/health");
    setText("health-status", health.status);
    setText("provider-status", health.provider);
    setText("resource-count", String(health.resource_count));
    setText("chunk-count", String(health.indexed_chunk_count));
  } catch (error) {
    setText("health-status", "Unavailable");
    setText("provider-status", "Error");
    setText("resource-count", "0");
    setText("chunk-count", "0");
  }
}

function buildLibraryCard(resource) {
  const article = document.createElement("article");
  article.className = "resource-item";
  article.innerHTML = `
    <p class="resource-title">${resource.title}</p>
    <p class="resource-meta">${resource.course_code} | ${resource.topic || "General"} | v${resource.version}</p>
    <p class="resource-excerpt">${resource.excerpt || "No excerpt available."}</p>
  `;
  return article;
}

async function loadResources(courseCode = "") {
  const suffix = courseCode ? `?course_code=${encodeURIComponent(courseCode)}` : "";
  try {
    const resources = await requestJson(`/resources${suffix}`);
    const container = document.getElementById("resource-list");
    container.innerHTML = "";

    if (!resources.length) {
      container.innerHTML = `<p class="empty-state">No indexed resources found for ${courseCode || "this filter"}.</p>`;
      return;
    }

    for (const resource of resources) {
      container.appendChild(buildLibraryCard(resource));
    }
  } catch (error) {
    setText("resource-list", error.message);
  }
}

function collectResourceForm() {
  return {
    lecturer_id: document.getElementById("resource-lecturer-id").value.trim(),
    course_code: document.getElementById("resource-course-code").value.trim(),
    title: document.getElementById("resource-title").value.trim(),
    topic: document.getElementById("resource-topic").value.trim() || null,
    week: document.getElementById("resource-week").value.trim() || null,
    semester: document.getElementById("resource-semester").value.trim() || null,
    academic_year: document.getElementById("resource-year").value.trim() || null,
    content_text: document.getElementById("resource-text").value.trim(),
    file: document.getElementById("resource-file").files[0] || null,
  };
}

async function submitResource(event) {
  event.preventDefault();
  const payload = collectResourceForm();

  try {
    let result;
    if (payload.file) {
      const formData = new FormData();
      formData.append("lecturer_id", payload.lecturer_id);
      formData.append("course_code", payload.course_code);
      formData.append("title", payload.title);
      formData.append("topic", payload.topic || "");
      formData.append("week", payload.week || "");
      formData.append("semester", payload.semester || "");
      formData.append("academic_year", payload.academic_year || "");
      formData.append("file", payload.file);
      result = await requestJson("/resources/upload", {
        method: "POST",
        body: formData,
      });
    } else {
      result = await requestJson("/resources/text", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
    }

    setText("resource-response", formatJson(result));
    await Promise.all([loadHealth(), loadResources(payload.course_code)]);
  } catch (error) {
    setText("resource-response", error.message);
  }
}

function collectChatPayload() {
  return {
    student_id: document.getElementById("chat-student-id").value.trim() || null,
    course_code: document.getElementById("chat-course-code").value.trim(),
    topic: document.getElementById("chat-topic").value.trim() || null,
    target_language: document.getElementById("chat-target-language").value.trim() || null,
    nationality: document.getElementById("chat-nationality").value.trim() || null,
    translate_response: document.getElementById("chat-translate").checked,
    question: document.getElementById("chat-question").value.trim(),
    bilingual: true,
  };
}

function renderCitations(citations) {
  if (!citations.length) {
    return "No citations returned.";
  }
  return citations
    .map((citation) => `${citation.title} (${citation.chunk_id})\n${citation.snippet}`)
    .join("\n\n");
}

function renderTranslation(result) {
  if (result.translation) {
    return result.translation.translated_text;
  }
  if (result.translation_error) {
    return result.translation_error;
  }
  return "Translation was not requested.";
}

async function submitChat(event) {
  event.preventDefault();
  try {
    const payload = collectChatPayload();
    const result = await requestJson("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    setText("chat-answer", result.answer_text || "No answer returned.");
    setText("chat-citations", renderCitations(result.citations || []));
    setText("chat-translation", renderTranslation(result));
    setText("chat-response", formatJson(result));
  } catch (error) {
    setText("chat-answer", "Chat failed.");
    setText("chat-citations", error.message);
    setText("chat-translation", error.message);
    setText("chat-response", error.message);
  }
}

function loadDemo() {
  document.getElementById("resource-lecturer-id").value = "L001";
  document.getElementById("resource-course-code").value = "CSC101";
  document.getElementById("resource-title").value = "Week 3 ERP Notes";
  document.getElementById("resource-topic").value = "ERP workflow";
  document.getElementById("resource-week").value = "Week 3";
  document.getElementById("resource-semester").value = "Semester 2";
  document.getElementById("resource-year").value = "2025/2026";
  document.getElementById("resource-text").value =
    "ERP integrates registration, finance, and academic workflows in one dashboard. Students can view course resources in the virtual room. Lecturers should tag notes by topic so the course assistant can retrieve the right explanation. Quiz readiness improves when students review indexed notes before attempting questions.";
  document.getElementById("chat-course-code").value = "CSC101";
  document.getElementById("chat-topic").value = "ERP workflow";
  document.getElementById("chat-question").value =
    "How do indexed notes help students prepare for quizzes in the ERP workflow?";
}

function clearChat() {
  setText("chat-answer", "Ask a question to see the course answer.");
  setText("chat-citations", "No citations yet.");
  setText("chat-translation", "No translated answer yet.");
  setText("chat-response", "No chat request sent yet.");
}

function bindEvents() {
  document.getElementById("resource-form").addEventListener("submit", submitResource);
  document.getElementById("chat-form").addEventListener("submit", submitChat);
  document.getElementById("load-demo").addEventListener("click", loadDemo);
  document.getElementById("clear-chat").addEventListener("click", clearChat);
  document.getElementById("refresh-library").addEventListener("click", () => loadResources());
  document.getElementById("apply-filter").addEventListener("click", () => {
    const courseCode = document.getElementById("resource-filter").value.trim();
    loadResources(courseCode);
  });
}

async function boot() {
  loadDemo();
  bindEvents();
  await Promise.all([loadHealth(), loadResources()]);
}

boot().catch((error) => {
  setText("chat-response", error.message);
});
