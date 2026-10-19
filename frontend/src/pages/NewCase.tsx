import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { PageBack } from "../lib/PageBackContext";
import { Hint } from "../components/Hint";
import { LocationAutocomplete } from "../components/LocationAutocomplete";
import { Spinner } from "../components/Skeleton";
import { Field } from "../components/forms/Field";
import { MissingList, MissingItem } from "../components/forms/MissingList";
import { useCases } from "../lib/CasesContext";

// Big tappable cards instead of a dropdown: every option visible at once,
// no fine motor control needed. Text only, no emoji.
const DISASTERS = [
  { value: "wildfire", label: "Wildfire / smoke", detail: "Fire, smoke, or ash damage" },
  { value: "flood", label: "Flood / water", detail: "Flooding, sewer backup, burst pipes" },
  { value: "hurricane", label: "Hurricane / wind", detail: "Severe wind or storm damage" },
  { value: "tornado", label: "Tornado", detail: "Tornado or funnel-cloud damage" },
  { value: "earthquake", label: "Earthquake", detail: "Structural or shaking damage" },
  { value: "other", label: "Something else", detail: "Hail, winter storm, or anything else" },
];

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

type FormState = {
  case_name: string;
  disaster_type: string;
  location: string;
  incident_date: string;
};

const EMPTY_FORM: FormState = {
  case_name: "",
  disaster_type: "wildfire",
  location: "",
  incident_date: "",
};

// One labelled step per screen. Kept short on purpose, three is the most a
// stressed person should have to hold in mind at once.
const STEPS = ["The disaster", "Where it happened", "When it happened"];

export default function NewCase() {
  const nav = useNavigate();
  const { cases, activeDraft, refresh } = useCases();
  // The draft is the autosave target. We either reuse the one already open or
  // create one on arrival, so half-entered answers survive an app close.
  const [draftId, setDraftId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // One question per screen lowers cognitive load in a crisis (Hick's law),
  // and a visibly-started progress bar makes finishing feel close (the
  // goal-gradient effect): we open on step 1 with a sensible disaster already
  // chosen, so it reads as "you've begun" rather than "a blank form awaits".
  const [step, setStep] = useState(0);
  // Until the draft is hydrated or created we show a spinner, otherwise an
  // empty form would flash over the user's saved answers for a moment.
  const [ready, setReady] = useState(false);
  const initRef = useRef(false);

  // On mount, hydrate from the active draft if there is one, otherwise create
  // a fresh draft to autosave into. Wait for cases to load first (null means
  // still loading) so we never create a duplicate draft.
  useEffect(() => {
    if (cases === null || initRef.current) return;
    initRef.current = true;
    (async () => {
      // Everyone we serve is in Alberta, so default the location to the
      // person's saved location and fall back to Alberta. It saves a step and
      // means recommendations work even before they reach the location screen.
      const me = await api.getMe().catch(() => null);
      const defaultLocation = (me?.profile.location ?? "").trim() || "Alberta";
      if (activeDraft) {
        setDraftId(activeDraft.id);
        setForm({
          case_name: activeDraft.case_name ?? "",
          disaster_type: activeDraft.disaster_type || "wildfire",
          location: (activeDraft.location ?? "").trim() || defaultLocation,
          incident_date: activeDraft.incident_date ?? "",
        });
        setReady(true);
        return;
      }
      try {
        const res = await api.createCase({ status: "draft", location: defaultLocation });
        setDraftId(res.case.id);
        setForm((f) => ({ ...f, location: defaultLocation }));
        await refresh();
      } catch (e: any) {
        setErr(e.message ?? String(e));
      } finally {
        setReady(true);
      }
    })();
  }, [cases, activeDraft, refresh]);

  // Debounced autosave: persist each field into the draft a beat after the
  // user stops typing. Best-effort, a failed save just retries on the next
  // edit and the Continue step writes the final values anyway.
  useEffect(() => {
    if (!ready || !draftId) return;
    const t = setTimeout(() => {
      api
        .updateCase(draftId, {
          // Fall back to the suggested name so an in-progress draft shows a
          // sensible label instead of "Untitled"; a name the user typed wins.
          case_name: form.case_name.trim() || suggestedName(),
          disaster_type: form.disaster_type,
          location: form.location,
          incident_date: form.incident_date || null,
        })
        .catch(() => {});
    }, 600);
    return () => clearTimeout(t);
  }, [form, ready, draftId]);

  function update<K extends keyof FormState>(k: K, v: string) {
    setForm((prev) => ({ ...prev, [k]: v }));
  }

  // Naming a case is a creative task nobody in crisis needs. Suggest one
  // from what we already know; the user can change it any time.
  function suggestedName(): string {
    const label = DISASTERS.find((d) => d.value === form.disaster_type)?.label ?? "Recovery";
    const place = form.location ? form.location.split(",")[0].trim() : "";
    const when = (form.incident_date ? new Date(form.incident_date + "T00:00:00") : new Date())
      .toLocaleDateString(undefined, { month: "long", year: "numeric" });
    return [label.split(" /")[0], place, when].filter(Boolean).join(", ");
  }

  // Continue promotes the draft to an active case and moves on to the plan.
  // If the draft never got created (for example the initial draft save failed),
  // we create the case outright from the filled-in form so the user is never
  // stuck behind a dead button.
  // What still blocks each step. Location is the one thing we truly need to
  // match local programs; everything else has a sensible default or is optional.
  const missingByStep: MissingItem[][] = [
    form.disaster_type ? [] : [{ id: "disaster-label", message: "Pick the kind of disaster" }],
    form.location.trim() ? [] : [{ id: "case-location", message: "Tell us where it happened (a city or area is enough)" }],
    [],
  ];
  const stepMissing = missingByStep[step] ?? [];
  const allMissing = missingByStep.flat();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    const fields = {
      case_name: form.case_name.trim() || suggestedName(),
      disaster_type: form.disaster_type,
      location: form.location,
      incident_date: form.incident_date || null,
      status: "active" as const,
    };
    try {
      const id = draftId
        ? (await api.updateCase(draftId, fields)).case.id
        : (await api.createCase(fields)).case.id;
      // Starting a case makes its location the person's location, so the rest
      // of the app (weather alerts, future cases) follows them. Best-effort.
      if (fields.location.trim()) {
        api.updateMe({ location: fields.location.trim() }).catch(() => {});
      }
      await refresh();
      nav(`/cases/${id}/recommendations`);
    } catch (e: any) {
      setErr(e.message ?? String(e));
      setBusy(false);
    }
  }

  // Discard soft-deletes the draft and returns to Prepare, so a recovery that
  // was started by mistake leaves nothing behind and the phase resets cleanly.
  async function discard() {
    if (!draftId) {
      nav("/prepare");
      return;
    }
    const ok = window.confirm(
      "Discard this case? Anything you entered here will be removed. You can always start again.",
    );
    if (!ok) return;
    setErr(null);
    setBusy(true);
    try {
      await api.deleteCase(draftId);
      await refresh();
      nav("/prepare");
    } catch (e: any) {
      setErr(e.message ?? String(e));
      setBusy(false);
    }
  }

  if (!ready) {
    return (
      <div className="container">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="container">
      <PageBack to="/prepare" label="Prepare" />
      <h1 style={{ marginTop: 16 }}>Tell us what happened</h1>
      <p className="warm-note">
        One thing at a time. Everything you type saves as you go, so you can
        step away and come back any time. You can add photos and documents
        afterward.
      </p>

      <ol className="wizard-steps" aria-label="Setup progress">
        {STEPS.map((label, i) => (
          <li
            key={label}
            className={`wizard-step${i < step ? " done" : i === step ? " current" : ""}`}
            aria-current={i === step ? "step" : undefined}
          >
            <span className="wizard-step-dot" aria-hidden>{i < step ? "✓" : i + 1}</span>
            <span className="wizard-step-label">{label}</span>
          </li>
        ))}
      </ol>
      <div
        className="meter"
        role="progressbar"
        aria-valuenow={step + 1}
        aria-valuemin={1}
        aria-valuemax={STEPS.length}
        aria-label="Setup progress"
      >
        <div className="meter-fill" style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <form onSubmit={submit}>
          {step === 0 && (
            <>
              <label id="disaster-label" tabIndex={-1}>What kind of disaster was it?<span className="req" aria-hidden="true"> *</span><span className="sr-only"> (required)</span></label>
              <p className="muted-strong" style={{ margin: "0 0 10px", fontSize: 14 }}>
                We've started you on the most common one, change it if it's not right.
              </p>
              <div className="choice-grid" role="radiogroup" aria-labelledby="disaster-label">
                {DISASTERS.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    role="radio"
                    aria-checked={form.disaster_type === d.value}
                    className={`choice-card${form.disaster_type === d.value ? " selected" : ""}`}
                    onClick={() => update("disaster_type", d.value)}
                  >
                    <span className="choice-title">{d.label}</span>
                    <span className="choice-detail">{d.detail}</span>
                  </button>
                ))}
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <label htmlFor="case-location">
                Where did it happen?<span className="req" aria-hidden="true"> *</span>
                <span className="sr-only"> (required)</span>{" "}
                <Hint text="We use this to match you with local emergency services and resources. We currently know Alberta best." />
              </label>
              <LocationAutocomplete
                id="case-location"
                required
                value={form.location}
                onChange={(v) => update("location", v)}
              />
              <p className="muted-strong" style={{ margin: "10px 0 0", fontSize: 13 }}>
                Not sure of the exact address? A city or area is plenty.
              </p>
            </>
          )}

          {step === 2 && (
            <>
              <label>
                When did it happen?{" "}
                <Hint text="Optional - an estimate is fine. It helps us flag insurance deadlines that are coming up soon." />
              </label>
              <div className="row" style={{ gap: 8, marginBottom: 8 }}>
                <button type="button" className="secondary chip-btn" onClick={() => update("incident_date", isoDaysAgo(0))}>
                  Today
                </button>
                <button type="button" className="secondary chip-btn" onClick={() => update("incident_date", isoDaysAgo(1))}>
                  Yesterday
                </button>
                <button type="button" className="secondary chip-btn" onClick={() => update("incident_date", isoDaysAgo(7))}>
                  About a week ago
                </button>
              </div>
              <input
                type="date"
                value={form.incident_date}
                aria-label="Date of the incident"
                onChange={(e) => update("incident_date", e.target.value)}
              />

              <Field
                label="Name for this case"
                value={form.case_name}
                onChange={(v) => update("case_name", v)}
                maxLength={80}
                placeholder={suggestedName()}
                help="Just a label to find it later. We'll pick a sensible one if you leave this blank, and you can change it anytime."
              />
            </>
          )}

          <MissingList items={step < STEPS.length - 1 ? stepMissing : allMissing} id="newcase-missing" />
          {err && <div className="error" role="alert">{err}</div>}
          <div className="row" style={{ marginTop: 20 }}>
            {step > 0 && (
              <button type="button" className="secondary" disabled={busy} onClick={() => setStep((s) => s - 1)}>
                Back
              </button>
            )}
            <span className="spacer" />
            {step < STEPS.length - 1 ? (
              <button type="button" className="big" disabled={stepMissing.length > 0} aria-describedby={stepMissing.length ? "newcase-missing" : undefined} onClick={() => setStep((s) => s + 1)}>
                Next
              </button>
            ) : (
              <button type="submit" disabled={busy || allMissing.length > 0} aria-describedby={allMissing.length ? "newcase-missing" : undefined} className="big">
                {busy ? "Setting things up…" : "Create my case"}
              </button>
            )}
          </div>
        </form>
      </div>

      <div style={{ marginTop: 16 }}>
        <button type="button" className="link-btn danger-text" disabled={busy} onClick={discard}>
          Discard this case
        </button>
      </div>
    </div>
  );
}
