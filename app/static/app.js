// Minimal fragment swapping: POST on click or submit, replace the board with
// the reply.
//
// This is the handful of HTMX behaviour the app actually uses, written out
// rather than pulled in. A draft-night tool has to work with no network and no
// build step, and vendoring a library to intercept events and swap innerHTML
// would cost more than it saves.

const BOARD = "board";

function restoreFocus() {
  // The board is replaced wholesale on every update, which destroys the input
  // the user was typing in. During an auction that input is the entire
  // interface: entry has to be name, price, Enter, name, price, Enter, with no
  // reach for the mouse between lots.
  const entry = document.querySelector(".entry-player");
  if (entry) {
    entry.value = "";
    entry.focus();
  }
}

async function post(url, body) {
  const board = document.getElementById(BOARD);
  board.classList.add("busy");
  try {
    const response = await fetch(url, { method: "POST", body: body || null });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    board.innerHTML = await response.text();
    restoreFocus();
  } catch (error) {
    // Never leave the board blank on a failure: a stale figure is recoverable,
    // an empty screen mid-auction is not.
    console.error(error);
    board.classList.add("error");
    setTimeout(() => board.classList.remove("error"), 1500);
  } finally {
    board.classList.remove("busy");
  }
}

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-post]");
  if (!trigger) return;
  event.preventDefault();
  const form = trigger.dataset.form;
  post(trigger.dataset.post, form ? new URLSearchParams(form) : null);
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-post-form]");
  if (!form) return;
  event.preventDefault();
  post(form.dataset.postForm, new FormData(form));
});

document.addEventListener("keydown", (event) => {
  // Undo is the one action worth a bare key, but never while typing: "u" is a
  // letter in half the player names on the board.
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName);
  if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "u") {
    event.preventDefault();
    post("/auction/undo");
  }
});
