// Click -> POST the page's visible text -> badge. The app scores in the background,
// so nothing here outlives the click (MV3 workers die when idle).
chrome.action.onClicked.addListener(async (tab) => {
  const badge = (text, color) => {
    chrome.action.setBadgeText({tabId: tab.id, text});
    chrome.action.setBadgeBackgroundColor({tabId: tab.id, color});
  };
  const {token} = await chrome.storage.local.get("token");
  if (!token) return chrome.runtime.openOptionsPage();
  try {
    // innerText: the rendered text, no scripts or hidden markup. The app caps text at 50k chars.
    const [{result: text}] = await chrome.scripting.executeScript(
      {target: {tabId: tab.id}, func: () => document.body.innerText.slice(0, 50000)});
    const r = await fetch("http://127.0.0.1:8000/capture", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-Capture-Token": token},
      body: JSON.stringify({url: tab.url, text}),
    });
    badge(r.ok ? "✓" : String(r.status), r.ok ? "#16a34a" : "#dc2626");
  } catch (e) {
    console.error(e);
    badge("✗", "#dc2626");  // app not running, or a page Chrome won't script (chrome://, Web Store)
  }
});
