const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api";

// FastAPI sends validation failures (422) as a list of {msg} objects, not a string.
function formatDetail(detail) {
  if (!Array.isArray(detail)) return detail;
  return detail.map((d) => String(d.msg).replace(/^Value error, /, "")).join(". ");
}

async function request(path, options = {}, token) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(formatDetail(body?.detail) || `Request failed: ${res.status}`);
  }
  return body;
}

// ---- Existing interview flow (unchanged shapes) ----

export const createSession = (sequenceId, candidateEmail) =>
  request("/sessions", {
    method: "POST",
    body: JSON.stringify({ sequence_id: sequenceId, candidate_email: candidateEmail || null }),
  });

export const getSession = (id) => request(`/sessions/${id}`);

export const askHelper = (id, question) =>
  request(`/sessions/${id}/helper`, { method: "POST", body: JSON.stringify({ question }) });

export const markReady = (id) => request(`/sessions/${id}/ready`, { method: "POST" });

export const submitAnswer = (id, text) =>
  request(`/sessions/${id}/answer`, { method: "POST", body: JSON.stringify({ text }) });

export const submitFollowup = (id, response) =>
  request(`/sessions/${id}/followup`, { method: "POST", body: JSON.stringify({ response }) });

export const advanceSession = (id) => request(`/sessions/${id}/advance`, { method: "POST" });

export const getResults = (id) => request(`/sessions/${id}/results`);

// NEW: force a session to completed immediately (timer expiry or voluntary "End Test").
export const endSession = (id) => request(`/sessions/${id}/end`, { method: "POST" });

// ---- Recruiter accounts ----

export const recruiterSignup = (email, password) =>
  request("/recruiters/signup", { method: "POST", body: JSON.stringify({ email, password }) });

export const recruiterLogin = (email, password) =>
  request("/recruiters/login", { method: "POST", body: JSON.stringify({ email, password }) });

export const recruiterLogout = (token) => request("/recruiters/logout", { method: "POST" }, token);

export const getRecruiterMe = (token) => request("/recruiters/me", {}, token);

// ---- Candidate accounts ----

export const candidateSignup = (email, password) =>
  request("/candidates/signup", { method: "POST", body: JSON.stringify({ email, password }) });

export const candidateLogin = (email, password) =>
  request("/candidates/login", { method: "POST", body: JSON.stringify({ email, password }) });

export const candidateLogout = (token) => request("/candidates/logout", { method: "POST" }, token);

export const getCandidateMe = (token) => request("/candidates/me", {}, token);

// ---- Sequences (recruiter) ----

export const listSequences = (token) => request("/sequences", {}, token);

// ---- Assessments / OAs (recruiter) ----

export const createAssessment = (token, sequenceId, durationMinutes) =>
  request(
    "/assessments",
    {
      method: "POST",
      body: JSON.stringify({ sequence_id: sequenceId, duration_minutes: durationMinutes }),
    },
    token
  );

export const listAssessments = (token) => request("/assessments", {}, token);

export const getAssessment = (token, id) => request(`/assessments/${id}`, {}, token);

export const closeAssessment = (token, id) =>
  request(`/assessments/${id}/close`, { method: "POST" }, token);

export const getAssessmentSessions = (token, id) => request(`/assessments/${id}/sessions`, {}, token);

// ---- Join an assessment (candidate) ----

export const joinAssessment = (token, shareToken) =>
  request(
    "/assessments/join",
    { method: "POST", body: JSON.stringify({ share_token: shareToken }) },
    token
  );
