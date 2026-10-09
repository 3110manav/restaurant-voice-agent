(() => {
  const sessionId = sessionStorage.getItem("voice-agent-session") || crypto.randomUUID();
  sessionStorage.setItem("voice-agent-session", sessionId);

  const state = {
    persona: "online",
    transcripts: { online: [], waiter: [] },
    cart: { online: [], waiter: [] },
    serviceLog: { online: [], waiter: [] },
  };

  const el = {
    transcript: document.getElementById("transcript"),
    micBtn: document.getElementById("micBtn"),
    micIcon: document.getElementById("micIcon"),
    textForm: document.getElementById("textForm"),
    textInput: document.getElementById("textInput"),
    status: document.getElementById("status"),
    cartList: document.getElementById("cartList"),
    cartTotal: document.getElementById("cartTotal"),
    serviceLogPanel: document.getElementById("serviceLogPanel"),
    serviceLogList: document.getElementById("serviceLogList"),
    personaBtns: document.querySelectorAll(".persona-btn"),
  };

  function setStatus(text) {
    el.status.textContent = text;
  }

  function addMessage(role, text) {
    state.transcripts[state.persona].push({ role, text });
    renderTranscript();
  }

  function renderTranscript() {
    el.transcript.innerHTML = "";
    for (const msg of state.transcripts[state.persona]) {
      const div = document.createElement("div");
      div.className = `msg ${msg.role}`;
      div.textContent = msg.text;
      el.transcript.appendChild(div);
    }
    el.transcript.scrollTop = el.transcript.scrollHeight;
  }

  function renderCart() {
    const cart = state.cart[state.persona];
    el.cartList.innerHTML = "";
    if (!cart.length) {
      el.cartList.innerHTML = '<li class="empty">Empty</li>';
      el.cartTotal.textContent = "";
      return;
    }
    let total = 0;
    for (const line of cart) {
      total += line.price * line.quantity;
      const li = document.createElement("li");
      li.innerHTML = `<span>${line.quantity} x ${line.name}</span><span>$${(line.price * line.quantity).toFixed(2)}</span>`;
      el.cartList.appendChild(li);
    }
    el.cartTotal.textContent = `Total: $${total.toFixed(2)}`;
  }

  function renderServiceLog() {
    const log = state.serviceLog[state.persona];
    el.serviceLogList.innerHTML = "";
    if (!log.length) {
      el.serviceLogList.innerHTML = '<li class="empty">None yet</li>';
      return;
    }
    for (const entry of log) {
      const li = document.createElement("li");
      const label = entry.type.replace(/_/g, " ");
      li.innerHTML = `<span>${label}${entry.details ? ": " + entry.details : ""}</span>`;
      el.serviceLogList.appendChild(li);
    }
  }

  function applyPersonaUi() {
    el.personaBtns.forEach((btn) => btn.classList.toggle("active", btn.dataset.persona === state.persona));
    el.serviceLogPanel.hidden = state.persona !== "waiter";
    el.textInput.placeholder =
      state.persona === "waiter" ? "e.g. bring me some water, or the bill..." : "Or type your order...";
    renderTranscript();
    renderCart();
    renderServiceLog();
  }

  el.personaBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.persona = btn.dataset.persona;
      applyPersonaUi();
    });
  });

  function playAudioBase64(b64) {
    if (!b64) return;
    const audio = new Audio(`data:audio/wav;base64,${b64}`);
    audio.play().catch(() => {});
  }

  async function sendText(message) {
    addMessage("user", message);
    setStatus("Thinking...");
    try {
      const resp = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message, persona: state.persona }),
      });
      if (!resp.ok) throw new Error(`server error ${resp.status}`);
      const data = await resp.json();
      addMessage("agent", data.reply);
      state.cart[state.persona] = data.cart;
      state.serviceLog[state.persona] = data.service_log;
      renderCart();
      renderServiceLog();
      setStatus("");
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  }

  el.textForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = el.textInput.value.trim();
    if (!text) return;
    el.textInput.value = "";
    sendText(text);
  });

  // --- mic recording (push to talk) ---
  let mediaRecorder = null;
  let chunks = [];
  let recording = false;

  async function toggleRecording() {
    if (!recording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
        mediaRecorder.onstop = onRecordingStop;
        mediaRecorder.start();
        recording = true;
        el.micBtn.classList.add("recording");
        setStatus("Recording... click again to stop.");
      } catch (err) {
        setStatus(`Mic error: ${err.message}`);
      }
    } else {
      mediaRecorder.stop();
      mediaRecorder.stream.getTracks().forEach((t) => t.stop());
      recording = false;
      el.micBtn.classList.remove("recording");
    }
  }

  async function onRecordingStop() {
    const blob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
    setStatus("Transcribing...");
    const form = new FormData();
    form.append("audio", blob, "recording.webm");
    try {
      const resp = await fetch(`/chat/voice?session_id=${encodeURIComponent(sessionId)}&persona=${encodeURIComponent(state.persona)}`, {
        method: "POST",
        body: form,
      });
      if (!resp.ok) throw new Error(`server error ${resp.status}`);
      const data = await resp.json();
      if (!data.transcript) {
        setStatus("Didn't catch that, try again.");
        return;
      }
      addMessage("user", data.transcript);
      addMessage("agent", data.reply);
      state.cart[state.persona] = data.cart;
      state.serviceLog[state.persona] = data.service_log;
      renderCart();
      renderServiceLog();
      setStatus("");
      playAudioBase64(data.reply_audio_wav_base64);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  }

  el.micBtn.addEventListener("click", toggleRecording);

  applyPersonaUi();
  addMessage("system", "Type or use the mic to start. Switch tabs above for the waiter persona.");
})();
