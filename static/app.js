const state = {
  languages: [],
};

function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function fillLanguageSelect(selectId, includeAuto) {
  const select = document.getElementById(selectId);
  if (!select) return;

  const currentValue = select.value;
  select.innerHTML = "";

  if (includeAuto) {
    const autoOption = document.createElement("option");
    autoOption.value = "";
    autoOption.textContent = "Auto from profile or nationality";
    select.appendChild(autoOption);
  }

  for (const language of state.languages) {
    const option = document.createElement("option");
    option.value = language.code;
    option.textContent = `${language.name} (${language.code})`;
    select.appendChild(option);
  }

  if (currentValue) {
    select.value = currentValue;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || "Request failed";
    throw new Error(detail);
  }
  return payload;
}

async function loadHealth() {
  try {
    const health = await requestJson("/health");
    setText("health-status", health.status);
    setText("provider-status", health.provider);
    setText("language-count", String(health.supported_languages.length));
  } catch (error) {
    setText("health-status", "Unavailable");
    setText("provider-status", "Error");
    setText("language-count", "0");
  }
}

async function loadLanguages() {
  state.languages = await requestJson("/languages");
  fillLanguageSelect("profile-language", false);
  fillLanguageSelect("glossary-language", false);
  fillLanguageSelect("translate-language-override", true);

  const glossaryLanguage = document.getElementById("glossary-language");
  glossaryLanguage.value = "sw";
}

function collectProfilePayload() {
  return {
    student_id: document.getElementById("profile-student-id").value.trim(),
    nationality: document.getElementById("profile-nationality").value.trim(),
    preferred_language: document.getElementById("profile-language").value || null,
  };
}

function collectGlossaryPayload() {
  const courseCode = document.getElementById("glossary-course-code").value.trim();
  const source = document.getElementById("glossary-source").value.trim();
  const language = document.getElementById("glossary-language").value;
  const target = document.getElementById("glossary-target").value.trim();

  return {
    courseCode,
    body: {
      terms: [
        {
          source,
          targets: {
            [language]: target,
          },
        },
      ],
    },
  };
}

function collectTranslationPayload() {
  return {
    student_id: document.getElementById("translate-student-id").value.trim(),
    course_code: document.getElementById("translate-course-code").value.trim() || null,
    content_type: document.getElementById("translate-content-type").value,
    target_language: document.getElementById("translate-language-override").value || null,
    bilingual: document.getElementById("translate-bilingual").checked,
    text: document.getElementById("translate-text").value.trim(),
  };
}

function renderTranslation(result) {
  setText("translated-text", result.translated_text || "No translated text returned.");

  if (result.bilingual_text) {
    setText(
      "bilingual-text",
      `English:\n${result.bilingual_text.source}\n\nTranslated:\n${result.bilingual_text.translated}`,
    );
  } else {
    setText("bilingual-text", "Bilingual output was disabled for this request.");
  }

  const metaLines = [
    `Provider: ${result.provider}`,
    `Target Language: ${result.target_language.name} (${result.target_language.code})`,
    `Resolved By: ${result.target_language.resolution_source}`,
    `Cache Hit: ${result.cache_hit}`,
    `Glossary Terms Applied: ${result.glossary_terms_applied.join(", ") || "None"}`,
    `Translated At: ${result.translated_at}`,
  ];
  setText("translation-meta", metaLines.join("\n"));
  setText("translation-response", formatJson(result));
}

function clearTranslationResult() {
  setText("translated-text", "Run a translation to see output.");
  setText("bilingual-text", "No bilingual output yet.");
  setText("translation-meta", "No translation metadata yet.");
  setText("translation-response", "No translation request sent yet.");
}

function loadSwahiliDemo() {
  document.getElementById("profile-student-id").value = "NLP001";
  document.getElementById("profile-nationality").value = "Kenya";
  document.getElementById("profile-language").value = "";
  document.getElementById("translate-student-id").value = "NLP001";
  document.getElementById("translate-course-code").value = "CSC101";
  document.getElementById("translate-language-override").value = "";
  document.getElementById("translate-text").value = "The ERP quiz is available on the dashboard.";
  document.getElementById("glossary-course-code").value = "CSC101";
  document.getElementById("glossary-source").value = "quiz";
  document.getElementById("glossary-language").value = "sw";
  document.getElementById("glossary-target").value = "jaribio";
}

function loadFrenchDemo() {
  document.getElementById("profile-student-id").value = "NLP002";
  document.getElementById("profile-nationality").value = "Kenya";
  document.getElementById("profile-language").value = "fr";
  document.getElementById("translate-student-id").value = "NLP002";
  document.getElementById("translate-course-code").value = "CSC101";
  document.getElementById("translate-language-override").value = "";
  document.getElementById("translate-text").value = "The ERP quiz is available on the dashboard.";
}

function bindEvents() {
  document.getElementById("profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await requestJson("/profiles", {
        method: "POST",
        body: JSON.stringify(collectProfilePayload()),
      });
      setText("profile-response", formatJson(result));
      document.getElementById("translate-student-id").value = result.student_id;
    } catch (error) {
      setText("profile-response", error.message);
    }
  });

  document.getElementById("glossary-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = collectGlossaryPayload();
    try {
      const result = await requestJson(`/glossary/${encodeURIComponent(payload.courseCode)}`, {
        method: "POST",
        body: JSON.stringify(payload.body),
      });
      setText("glossary-response", formatJson(result));
      document.getElementById("translate-course-code").value = payload.courseCode;
    } catch (error) {
      setText("glossary-response", error.message);
    }
  });

  document.getElementById("translation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await requestJson("/translate", {
        method: "POST",
        body: JSON.stringify(collectTranslationPayload()),
      });
      renderTranslation(result);
    } catch (error) {
      setText("translation-response", error.message);
      setText("translated-text", "Translation failed.");
      setText("bilingual-text", "Check the raw response section for the error message.");
      setText("translation-meta", error.message);
    }
  });

  document.getElementById("load-sample-sw").addEventListener("click", loadSwahiliDemo);
  document.getElementById("load-sample-fr").addEventListener("click", loadFrenchDemo);
  document.getElementById("clear-results").addEventListener("click", clearTranslationResult);
}

async function boot() {
  await Promise.all([loadHealth(), loadLanguages()]);
  bindEvents();
  loadSwahiliDemo();
}

boot().catch((error) => {
  setText("translation-response", error.message);
});
