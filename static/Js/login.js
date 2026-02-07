document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  const errorEl = document.getElementById("error");

  errorEl.textContent = "";

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email, password })
    });

    const data = await res.json();

    if (!res.ok || !data.token) {
      errorEl.textContent = "Invalid email or password";
      return;
    }

    // 🔐 STORE TOKEN
    localStorage.setItem("token", data.token);

    // ✅ Redirect after login
    window.location.href = "/dashboard";
  } catch (err) {
    errorEl.textContent = "Server error. Try again.";
  }
});
