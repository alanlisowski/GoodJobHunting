const input = document.getElementById("token");
chrome.storage.local.get("token").then(({token}) => { input.value = token ?? ""; });
document.getElementById("save").onclick = async () => {
  await chrome.storage.local.set({token: input.value.trim()});
  document.getElementById("status").textContent = "Saved.";
};
