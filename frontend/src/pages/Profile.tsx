import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, MeResponse } from "../api";
import { PageBack } from "../lib/PageBackContext";
import { Hint } from "../components/Hint";
import { LocationAutocomplete } from "../components/LocationAutocomplete";
import { useAuth } from "../auth/AuthContext";
import { Field } from "../components/forms/Field";

const CHECK_LABELS: Record<string, { label: string; to?: string }> = {
  profile_name: { label: "Add your name to your profile" },
  profile_location: { label: "Add your location" },
  has_case: { label: "Start your first case", to: "/cases/new" },
  has_document: { label: "Upload your first document", to: "/documents" },
  has_policy_document: { label: "Upload your insurance policy", to: "/documents" },
  has_inventory_item: { label: "Add at least one item to your inventory" },
};

export default function Profile() {
  const { user } = useAuth();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState({ full_name: "", location: "" });

  useEffect(() => {
    api.getMe()
      .then((r) => {
        setMe(r);
        setForm({
          full_name: r.profile.full_name ?? "",
          location: r.profile.location ?? "",
        });
      })
      .catch((e) => setErr(String(e)));
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    setSaved(false);
    try {
      const r = await api.updateMe(form);
      setMe(r);
      setSaved(true);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container" style={{ maxWidth: 720 }}>
      <PageBack to="/dashboard" label="Dashboard" />
      <h1 style={{ marginTop: 16 }}>Your profile</h1>
      <p className="warm-note" style={{ marginTop: 8 }}>
        A little about you, so we can tailor the help to your situation.
      </p>

      {err && <div className="error">{err}</div>}

      {me && (
        <>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Recovery readiness</h3>
            <p className="muted-strong" style={{ marginTop: 0 }}>
              How prepared are you to make the most of your plan?
              {" "}
              <strong style={{ color: "var(--text)" }}>{me.readiness.percent}% complete</strong>
              {" "}({me.readiness.completed} of {me.readiness.total})
            </p>
            <div
              role="progressbar"
              aria-valuenow={me.readiness.percent}
              aria-valuemin={0}
              aria-valuemax={100}
              style={{
                background: "var(--panel-2)",
                borderRadius: 10,
                height: 14,
                overflow: "hidden",
                border: "1px solid var(--border)",
                marginTop: 8,
              }}
            >
              <div
                style={{
                  width: `${me.readiness.percent}%`,
                  height: "100%",
                  background: "linear-gradient(90deg, var(--accent) 0%, var(--focus) 100%)",
                  transition: "width 0.4s ease",
                }}
              />
            </div>

            <ul style={{ listStyle: "none", padding: 0, marginTop: 18 }}>
              {me.readiness.checks.map((c) => {
                const meta = CHECK_LABELS[c.key] ?? { label: c.key };
                const node = (
                  <li key={c.key} style={{
                    padding: "8px 0",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: 15,
                    color: c.done ? "var(--text)" : "var(--muted-strong)",
                  }}>
                    <span
                      aria-hidden
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 22, height: 22, borderRadius: "50%",
                        background: c.done ? "var(--accent)" : "var(--panel-2)",
                        border: c.done ? "none" : "1px solid var(--border)",
                        color: "white", fontSize: 13, fontWeight: 700,
                      }}
                    >
                      {c.done ? "✓" : ""}
                    </span>
                    {meta.to && !c.done ? (
                      <Link to={meta.to} style={{ textDecoration: "underline", color: "var(--focus)" }}>
                        {meta.label}
                      </Link>
                    ) : (
                      <span>{meta.label}</span>
                    )}
                  </li>
                );
                return node;
              })}
            </ul>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>About you</h3>
            <form onSubmit={save}>
              <Field
                label="Your name"
                value={form.full_name}
                onChange={(v) => setForm({ ...form, full_name: v })}
                maxLength={100}
                autoComplete="name"
                placeholder="e.g. Jane Doe"
                help="Only you see this. We use it to greet you and to fill in claim forms later."
              />

              <label htmlFor="profile-location">
                Where you live{" "}
                <Hint text="Used to match you with local emergency services and resources. We currently know Alberta best." />
              </label>
              <LocationAutocomplete
                id="profile-location"
                value={form.location}
                onChange={(v) => setForm({ ...form, location: v })}
              />

              <label htmlFor="profile-email">Email</label>
              <input id="profile-email" value={user?.email ?? ""} disabled aria-describedby="profile-email-help" />
              <p id="profile-email-help" className="field-help">This is the email you signed in with.</p>

              {saved && (
                <p className="muted-strong" role="status" style={{ marginTop: 10, color: "var(--focus)" }}>
                  Saved.
                </p>
              )}
              <div style={{ marginTop: 18 }}>
                <button type="submit" disabled={busy}>{busy ? "Saving..." : "Save"}</button>
              </div>
            </form>
          </div>
        </>
      )}
    </div>
  );
}
