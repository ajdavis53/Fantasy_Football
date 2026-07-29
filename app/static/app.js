// Minimal fragment swapping: POST on click, replace the board with the reply.
//
// This is the handful of HTMX behaviour the app actually uses, written out
// rather than pulled in. A draft-night tool has to work with no network and no
// build step, and vendoring a library to intercept clicks and swap innerHTML
// would cost more than it saves.

const BOARD = "board";

async function post(url, body) {
  const board = document.getElementById(BOARD);
  board.classList.add("busy");
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: body ? { "Content-Type": "application/x-www-form-urlencoded" } : {},
      body: body || null,
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    board.innerHTML = await response.text();
  } catch (error) {
    // Never leave the board blank on a failure: a stale figure is recoverable,
    // an empty screen mid-decision is not.
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
  post(trigger.dataset.post, trigger.dataset.form);
});
