const devicesEl = document.querySelector("#devices");
const messagesEl = document.querySelector("#messages");
const gadgetStatusEl = document.querySelector("#gadgetStatus");
const forwardStatusEl = document.querySelector("#forwardStatus");
const connectionStatusEl = document.querySelector("#connectionStatus");
const setupGadgetButton = document.querySelector("#setupGadget");
const startGadgetButton = document.querySelector("#startGadget");
const reconnectGadgetButton = document.querySelector("#reconnectGadget");
const stopGadgetButton = document.querySelector("#stopGadget");
const testKeyButton = document.querySelector("#testKey");
const testMouseButton = document.querySelector("#testMouse");
const startForwardButton = document.querySelector("#startForward");
const stopForwardButton = document.querySelector("#stopForward");
const virtualTextInput = document.querySelector("#virtualText");
const sendTextButton = document.querySelector("#sendText");
const virtualButtons = [
  sendTextButton,
  ...document.querySelectorAll("[data-key], [data-move], [data-click], [data-wheel]"),
];

let statusCache = null;

function showMessage(message) {
  if (!message) {
    messagesEl.hidden = true;
    messagesEl.textContent = "";
    return;
  }
  messagesEl.hidden = false;
  messagesEl.textContent = message;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

function setBusy(button, busy) {
  button.disabled = busy;
}

function renderStatus(status) {
  statusCache = status;
  const gadget = status.gadget;
  connectionStatusEl.textContent = gadget.active ? "Client connected" : gadget.bound ? "Not connected" : "Host port inactive";
  connectionStatusEl.className = gadget.active ? "status ok" : "status warn";

  if (!gadget.configured) {
    gadgetStatusEl.textContent = "Not set up yet.";
  } else if (gadget.active) {
    const state = gadget.udc_state ? `, status: ${gadget.udc_state}` : "";
    gadgetStatusEl.textContent = `Active through ${gadget.udc}${state}. HID: ${gadget.keyboard_ready && gadget.mouse_ready ? "ready" : "not ready"}.`;
  } else if (gadget.bound) {
    const state = gadget.udc_state ? `status: ${gadget.udc_state}` : "unknown status";
    gadgetStatusEl.textContent = `Gadget is bound, but the client is not connected (${state}).`;
  } else if (!gadget.udc_available) {
    gadgetStatusEl.textContent =
      "Set up, but no USB Device Controller was found. Check dwc2, reboot, and the USB/OTG data port.";
  } else {
    gadgetStatusEl.textContent = "Set up, but not bound to the host port.";
  }

  setupGadgetButton.disabled = gadget.configured;
  setupGadgetButton.textContent = gadget.configured ? "Gadget set up" : "Set up gadget";
  startGadgetButton.disabled = gadget.bound || !gadget.udc_available;
  reconnectGadgetButton.disabled = !gadget.bound;
  const clientReady = gadget.active;
  const keyboardWritable = gadget.active && gadget.keyboard_ready;
  const mouseWritable = gadget.active && gadget.mouse_ready;
  testKeyButton.disabled = !keyboardWritable;
  testMouseButton.disabled = !mouseWritable;
  virtualButtons.forEach((button) => {
    const needsMouse = button.dataset.move !== undefined || button.dataset.click !== undefined || button.dataset.wheel !== undefined;
    button.disabled = needsMouse ? !mouseWritable : !keyboardWritable;
  });
  virtualTextInput.disabled = !keyboardWritable;
  stopGadgetButton.disabled = !gadget.configured;

  const forwarding = status.forwarding;
  if (forwarding.running) {
    forwardStatusEl.textContent = `${forwarding.event_paths.length} input channel(s) are being forwarded.`;
  } else {
    forwardStatusEl.textContent = "No forwarding is active.";
  }

  startForwardButton.disabled = !clientReady;
  stopForwardButton.disabled = !forwarding.running;

  if (forwarding.errors.length) {
    showMessage(forwarding.errors.join(" | "));
  }
}

function renderDevices(devices) {
  devicesEl.innerHTML = "";
  if (!devices.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No USB devices detected.";
    devicesEl.append(empty);
    return;
  }

  for (const device of devices) {
    const row = document.createElement("article");
    row.className = "device";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = device.selected;
    checkbox.disabled = device.capability !== "hid_input";
    checkbox.addEventListener("change", async () => {
      try {
        showMessage("");
        await api("/api/select", {
          method: "POST",
          body: JSON.stringify({ sys_name: device.sys_name, enabled: checkbox.checked }),
        });
        await refresh();
      } catch (error) {
        checkbox.checked = !checkbox.checked;
        showMessage(error.message);
      }
    });

    const main = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = device.name;
    const meta = document.createElement("div");
    meta.className = "meta";
    const inputChannels = device.input_channels || [];
    const forwardedChannels = inputChannels.filter((channel) => channel.forwardable);
    const channelText = inputChannels.length
      ? inputChannels
          .map((channel) => `${channel.path} ${channel.label}${channel.forwardable ? "" : " (not forwarded)"}`)
          .join(", ")
      : "no input event";
    for (const text of [
      `ID ${device.vendor_id}:${device.product_id}`,
      `Port ${device.sys_name}`,
      `Bus ${device.busnum || "-"} device ${device.devnum || "-"}`,
      `${forwardedChannels.length} forwardable channel(s)`,
      channelText,
    ]) {
      const span = document.createElement("span");
      span.textContent = text;
      meta.append(span);
    }
    main.append(title, meta);

    const badge = document.createElement("div");
    badge.className = device.capability === "hid_input" ? "badge ok" : "badge warn";
    badge.textContent = device.capability_label;

    row.append(checkbox, main, badge);
    devicesEl.append(row);
  }
}

async function refresh() {
  try {
    showMessage("");
    const [status, devices] = await Promise.all([api("/api/status"), api("/api/devices")]);
    renderStatus(status);
    renderDevices(devices.devices);
  } catch (error) {
    connectionStatusEl.textContent = "Agent unreachable";
    connectionStatusEl.className = "status warn";
    showMessage(error.message);
  }
}

async function postAction(buttonId, path) {
  const button = document.querySelector(buttonId);
  setBusy(button, true);
  try {
    showMessage("");
    const payload = await api(path, { method: "POST", body: "{}" });
    let message = "";
    if (path.includes("/forward/start") && payload.unsupported && payload.unsupported.length) {
      message = `Not forwardable: ${payload.unsupported.join(", ")}`;
    }
    if (payload.action && payload.action.message) {
      message = payload.action.message;
    }
    await refresh();
    showMessage(message);
  } catch (error) {
    showMessage(error.message);
    if (statusCache) {
      renderStatus(statusCache);
    } else {
      setBusy(button, false);
    }
  }
}

async function postPayload(button, path, payload) {
  setBusy(button, true);
  try {
    showMessage("");
    const result = await api(path, { method: "POST", body: JSON.stringify(payload) });
    let message = "";
    if (result.skipped && result.skipped.length) {
      message = `Not sent: ${result.skipped.join("")}`;
    }
    await refresh();
    showMessage(message);
  } catch (error) {
    showMessage(error.message);
    if (statusCache) {
      renderStatus(statusCache);
    } else {
      setBusy(button, false);
    }
  }
}

setupGadgetButton.addEventListener("click", () => postAction("#setupGadget", "/api/gadget/setup"));
startGadgetButton.addEventListener("click", () => postAction("#startGadget", "/api/gadget/start"));
reconnectGadgetButton.addEventListener("click", () => postAction("#reconnectGadget", "/api/gadget/reconnect"));
testKeyButton.addEventListener("click", () => postAction("#testKey", "/api/test/key"));
testMouseButton.addEventListener("click", () => postAction("#testMouse", "/api/test/mouse"));
stopGadgetButton.addEventListener("click", () => postAction("#stopGadget", "/api/gadget/stop"));
startForwardButton.addEventListener("click", () => postAction("#startForward", "/api/forward/start"));
stopForwardButton.addEventListener("click", () => postAction("#stopForward", "/api/forward/stop"));
document.querySelector("#refresh").addEventListener("click", refresh);

sendTextButton.addEventListener("click", async () => {
  await postPayload(sendTextButton, "/api/virtual/type", { text: virtualTextInput.value });
});

virtualTextInput.addEventListener("keydown", async (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    await postPayload(sendTextButton, "/api/virtual/type", { text: virtualTextInput.value });
  }
});

for (const button of document.querySelectorAll("[data-key]")) {
  button.addEventListener("click", () => postPayload(button, "/api/virtual/key", { key: button.dataset.key }));
}

for (const button of document.querySelectorAll("[data-move]")) {
  button.addEventListener("click", () => {
    const [x, y] = button.dataset.move.split(",").map((value) => Number.parseInt(value, 10));
    postPayload(button, "/api/virtual/mouse", { x, y });
  });
}

for (const button of document.querySelectorAll("[data-click]")) {
  button.addEventListener("click", () => postPayload(button, "/api/virtual/click", { button: button.dataset.click }));
}

for (const button of document.querySelectorAll("[data-wheel]")) {
  button.addEventListener("click", () => {
    postPayload(button, "/api/virtual/mouse", { x: 0, y: 0, wheel: Number.parseInt(button.dataset.wheel, 10) });
  });
}

refresh();
setInterval(refresh, 2500);
