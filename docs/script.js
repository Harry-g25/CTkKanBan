const sidebar = document.getElementById("sidebar");
const overlay = document.getElementById("overlay");
const hamburger = document.getElementById("hamburger");
const backToTop = document.getElementById("back-to-top");
const navLinks = [...document.querySelectorAll(".sidebar-nav a")];
const searchInput = document.getElementById("docs-search-input");
const searchResults = document.getElementById("docs-search-results");
const searchStatus = document.getElementById("docs-search-status");

function setMenuOpen(open) {
  sidebar?.classList.toggle("is-open", open);
  overlay?.classList.toggle("is-visible", open);
  hamburger?.setAttribute("aria-expanded", String(open));
}

hamburger?.addEventListener("click", () => {
  setMenuOpen(!sidebar?.classList.contains("is-open"));
});

overlay?.addEventListener("click", () => setMenuOpen(false));

navLinks.forEach((link) => {
  link.addEventListener("click", () => {
    if (window.innerWidth <= 768) {
      setMenuOpen(false);
    }
  });
});

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

const usedHeadingIds = new Set(
  [...document.querySelectorAll("[id]")].map((element) => element.id),
);

document.querySelectorAll(".doc-section h2, .doc-section h3, .doc-section h4").forEach((heading) => {
  if (heading.id) {
    return;
  }
  const base = slugify(heading.textContent || "") || "guide-section";
  let candidate = base;
  let suffix = 2;
  while (usedHeadingIds.has(candidate)) {
    candidate = `${base}-${suffix}`;
    suffix += 1;
  }
  heading.id = candidate;
  usedHeadingIds.add(candidate);
});

function nearestHeading(row) {
  const section = row.closest(".doc-section");
  if (!section) {
    return null;
  }
  const headings = [...section.querySelectorAll("h2, h3, h4")];
  const preceding = headings.filter(
    (heading) =>
      heading.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING,
  );
  return preceding[preceding.length - 1] || null;
}

const searchIndex = [
  ...[...document.querySelectorAll(".doc-section h2, .doc-section h3, .doc-section h4")].map(
    (heading) => ({
      title: (heading.textContent || "").trim(),
      context: heading.closest(".doc-section")?.querySelector("h2")?.textContent?.trim() || "Guide",
      target: heading.id,
      text: `${heading.textContent || ""} ${heading.parentElement?.textContent || ""}`.toLowerCase(),
    }),
  ),
  ...[...document.querySelectorAll(".doc-table tbody tr")].map((row) => {
    const heading = nearestHeading(row);
    const cells = [...row.querySelectorAll("td")];
    return {
      title: (cells[0]?.textContent || "Reference entry").trim(),
      context: (heading?.textContent || "API reference").trim(),
      target: heading?.id || row.closest(".doc-section")?.id || "hero",
      text: (row.textContent || "").toLowerCase(),
    };
  }),
];

function closeSearch({ clear = false } = {}) {
  if (searchResults) {
    searchResults.hidden = true;
    searchResults.replaceChildren();
  }
  if (searchStatus) {
    searchStatus.textContent = "";
  }
  if (clear && searchInput) {
    searchInput.value = "";
  }
}

function renderSearchResults() {
  if (!searchInput || !searchResults || !searchStatus) {
    return;
  }
  const query = searchInput.value.trim().toLowerCase();
  searchResults.replaceChildren();
  if (query.length < 2) {
    closeSearch();
    searchStatus.textContent = query ? "Type one more character" : "";
    return;
  }

  const terms = query.split(/\s+/).filter(Boolean);
  const matches = searchIndex
    .filter((item) => terms.every((term) => item.text.includes(term)))
    .sort((left, right) => {
      const leftTitle = left.title.toLowerCase();
      const rightTitle = right.title.toLowerCase();
      return Number(rightTitle.startsWith(query)) - Number(leftTitle.startsWith(query));
    })
    .slice(0, 12);

  searchStatus.textContent = matches.length
    ? `${matches.length} result${matches.length === 1 ? "" : "s"}`
    : "No matching reference entries";
  searchResults.hidden = false;

  if (!matches.length) {
    const empty = document.createElement("p");
    empty.className = "docs-search__empty";
    empty.textContent = "Try a method, option, callback, or database term.";
    searchResults.append(empty);
    return;
  }

  matches.forEach((item) => {
    const link = document.createElement("a");
    const title = document.createElement("strong");
    const context = document.createElement("span");
    link.href = `#${item.target}`;
    title.textContent = item.title;
    context.textContent = item.context;
    link.append(title, context);
    link.addEventListener("click", () => {
      closeSearch({ clear: true });
      if (window.innerWidth <= 768) {
        setMenuOpen(false);
      }
    });
    searchResults.append(link);
  });
}

searchInput?.addEventListener("input", renderSearchResults);
searchInput?.addEventListener("focus", renderSearchResults);
searchInput?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeSearch({ clear: true });
    searchInput.blur();
  }
});

document.addEventListener("keydown", (event) => {
  const target = event.target;
  const isTyping =
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target?.isContentEditable;
  if (event.key === "/" && !isTyping) {
    event.preventDefault();
    if (window.innerWidth <= 768) {
      setMenuOpen(true);
      window.setTimeout(() => searchInput?.focus(), 300);
    } else {
      searchInput?.focus();
    }
  }
});

document.addEventListener("click", (event) => {
  if (!(event.target instanceof Element) || !event.target.closest(".docs-search")) {
    closeSearch();
  }
});

const observedSections = [...document.querySelectorAll("section[id], header[id]")];
const sectionObserver = new IntersectionObserver(
  (entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((left, right) => right.intersectionRatio - left.intersectionRatio);
    if (!visible.length) {
      return;
    }

    const activeId = visible[0].target.id;
    navLinks.forEach((link) => {
      link.classList.toggle("is-active", link.getAttribute("href") === `#${activeId}`);
    });
  },
  {
    rootMargin: "-30% 0px -60% 0px",
    threshold: [0.05, 0.2, 0.5],
  },
);

observedSections.forEach((section) => sectionObserver.observe(section));

window.addEventListener("scroll", () => {
  backToTop?.classList.toggle("is-visible", window.scrollY > 500);
});

async function copyText(button, text) {
  const original = button.textContent;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      document.body.append(textArea);
      textArea.select();
      document.execCommand("copy");
      textArea.remove();
    }
    button.textContent = "Copied";
    button.classList.add("is-copied");
  } catch (_error) {
    button.textContent = "Copy failed";
  }

  window.setTimeout(() => {
    button.textContent = original;
    button.classList.remove("is-copied");
  }, 1400);
}

document.querySelectorAll(".copy-button").forEach((button) => {
  button.addEventListener("click", () => {
    const code = button.closest(".code-block")?.querySelector("code");
    if (code) {
      copyText(button, code.textContent || "");
    }
  });
});

const installCopy = document.getElementById("install-copy");
const installCommand = document.getElementById("install-command");
installCopy?.addEventListener("click", () => {
  copyText(installCopy, installCommand?.textContent || "");
});

document.querySelectorAll(".code-block").forEach((block) => {
  const language = block.querySelector(".code-block__header span")?.textContent?.trim().toLowerCase();
  const code = block.querySelector("pre code");
  if (language && code) {
    code.classList.add(`language-${language}`);
  }
});

if (window.hljs) {
  window.hljs.highlightAll();
}
