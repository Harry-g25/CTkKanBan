const sidebar = document.getElementById("sidebar");
const overlay = document.getElementById("overlay");
const hamburger = document.getElementById("hamburger");
const backToTop = document.getElementById("back-to-top");
const navLinks = [...document.querySelectorAll(".sidebar-nav a")];

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
