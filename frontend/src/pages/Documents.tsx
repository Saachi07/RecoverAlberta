import { AiNotice } from "../components/AiNotice";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, CoverageLimit, GeminiAnalysis, RichAnalysis, UserDocument } from "../api";
import { Spinner } from "../components/Skeleton";
import { PageBack } from "../lib/PageBackContext";
import { Modal, ConfirmDialog } from "../components/Modal";
import { useToast } from "../components/Toast";
import { useCases } from "../lib/CasesContext";
import { SourceQuote } from "../components/analysis/SourceQuote";
import { DisclaimerBanner } from "../components/analysis/DisclaimerBanner";
import { CoverageScopeCard } from "../components/analysis/CoverageScopeCard";
import { GlossaryCard } from "../components/analysis/GlossaryCard";
import { DeductibleCard } from "../components/analysis/DeductibleCard";
import "../styles/analysis.css";

// Phone photos are the default format of a disaster survivor's paperwork , 
// PDFs are accepted alongside JPG/PNG/WebP/HEIC.
const ACCEPTED = "application/pdf,.pdf,image/jpeg,image/png,image/webp,image/heic,image/heif";
const ACCEPTED_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
const ACCEPTED_EXT = [".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"];

const DOC_TYPES: { value: string; label: string }[] = [
  { value: "insurance_policy", label: "Insurance policy" },
  { value: "claim", label: "Claim" },
  { value: "id", label: "ID document" },
  { value: "deed", label: "Deed" },
  { value: "receipt", label: "Receipt" },
  { value: "invoice", label: "Invoice" },
  { value: "estimate", label: "Estimate" },
  { value: "correspondence", label: "Letter / correspondence" },
  { value: "other", label: "Something else" },
];

function isAccepted(file: File): boolean {
  const type = (file.type || "").toLowerCase();
  if (ACCEPTED_TYPES.includes(type)) return true;
  const name = file.name.toLowerCase();
  return ACCEPTED_EXT.some((ext) => name.endsWith(ext));
}

function richOf(d: UserDocument): RichAnalysis {
  return d.gemini_analysis?.analysis ?? {};
}

export default function Documents() {
  const toast = useToast();
  const { latest } = useCases();
  const [docs, setDocs] = useState<UserDocument[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [analyzingNew, setAnalyzingNew] = useState(false);
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [summaryFor, setSummaryFor] = useState<UserDocument | null>(null);
  const [editFor, setEditFor] = useState<UserDocument | null>(null);
  const [deleteFor, setDeleteFor] = useState<UserDocument | null>(null);
  const [deleted, setDeleted] = useState<UserDocument[] | null>(null);
  const [showDeleted, setShowDeleted] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);

  function load() {
    api.listMyDocuments().then((r) => setDocs(r.documents)).catch((e) => setErr(e.message ?? String(e)));
  }

  function loadDeleted() {
    api.listDeletedDocuments().then((r) => setDeleted(r.documents)).catch((e) => setErr(e.message ?? String(e)));
  }

  useEffect(load, []);

  function toggleDeleted() {
    const next = !showDeleted;
    setShowDeleted(next);
    if (next && deleted === null) loadDeleted();
  }

  async function restore(id: string) {
    setRestoring(id);
    setErr(null);
    try {
      await api.restoreDocument(id);
      loadDeleted();
      load();
      toast.show("Document restored.");
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setRestoring(null);
    }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!isAccepted(file)) {
      setErr(
        "That file type isn't supported yet. You can upload a PDF or a photo " +
        "(JPG, PNG, HEIC), a clear phone photo of the document works great.",
      );
      return;
    }
    setUploading(true);
    setProgress(0);
    setErr(null);
    try {
      const { document } = await api.uploadDocument(file, setProgress);
      // Auto-analyze. Don't fail the whole upload if analysis fails, the doc is saved.
      setAnalyzingNew(true);
      load();
      try {
        await api.analyzeDocument(document.id);
      } catch (e: any) {
        setErr(`Your document is saved, but we couldn't read it just now: ${e.message ?? e}. You can try "Analyze" on it again in a minute.`);
      } finally {
        setAnalyzingNew(false);
      }
      load();
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }

  async function reanalyze(id: string) {
    setAnalyzing(id);
    setErr(null);
    try {
      await api.analyzeDocument(id);
      load();
      toast.show("We've read the document and pulled out the important bits.");
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setAnalyzing(null);
    }
  }

  async function openDoc(id: string) {
    setOpening(id);
    try {
      const { url } = await api.getDocumentUrl(id);
      window.open(url, "_blank", "noreferrer");
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setOpening(null);
    }
  }

  async function confirmDelete() {
    if (!deleteFor) return;
    const doc = deleteFor;
    setDeleteFor(null);
    try {
      await api.deleteDocument(doc.id);
      load();
      if (deleted !== null) loadDeleted();
      toast.show(`Deleted "${doc.name}". You can restore it within 30 days.`);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    }
  }

  const inventoryHref = latest ? `/cases/${latest.id}/inventory` : "/cases/new";
  const planHref = latest ? `/cases/${latest.id}/recommendations` : "/cases/new";

  return (
    <div className="container">
      <PageBack to="/dashboard" label="Dashboard" />
      <div className="row" style={{ marginTop: 16 }}>
        <h1 style={{ margin: 0 }}>Your documents</h1>
      </div>
      <p className="warm-note" style={{ marginTop: 8 }}>
        Upload your insurance policy, claims, ID, deeds, anything you might
        need to reference. A PDF or a clear phone photo both work. We'll read
        each one and pull out the important bits.
      </p>

      <div className="card no-print">
        <h3 style={{ marginTop: 0 }}>Add a document</h3>
        <p className="muted-strong" style={{ marginTop: 0, fontSize: 14 }}>
          Pick a PDF or a photo of the document. We'll save it and analyze it
          automatically, no extra steps.
        </p>
        <input
          type="file"
          accept={ACCEPTED}
          onChange={onUpload}
          disabled={uploading || analyzingNew}
          aria-label="Choose a document to upload"
        />
        <AiNotice kind="document" />
        {uploading && (
          <div style={{ marginTop: 10 }}>
            <p className="muted-strong" style={{ margin: "0 0 6px" }} role="status">
              {progress < 100 ? `Uploading… ${progress}%` : "Upload complete, saving…"}
            </p>
            <div className="meter">
              <div className="meter-fill" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}
        {analyzingNew && (
          <p className="muted-strong" style={{ marginTop: 10 }} role="status">
            Saved. Now reading your document, this can take a minute, and it's
            safe to keep using the app while we work.
          </p>
        )}
        {err && <div className="error">{err}</div>}
      </div>

      <h3>You have {docs?.length ?? 0} document{docs?.length === 1 ? "" : "s"}</h3>
      {docs === null && !err && <Spinner />}
      {docs && docs.length === 0 && (
        <p className="muted-strong">Nothing here yet. Upload one above to get started.</p>
      )}
      {docs && docs.length > 0 && (
        <table className="tbl tbl-cards">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>What we found</th>
              <th>Uploaded</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => {
              const rich = richOf(d);
              const deadlineCount = rich.deadlines?.length ?? 0;
              const flaggedCount = rich.flagged_issues?.length ?? 0;
              return (
                <tr key={d.id}>
                  <td data-label="Name">{d.name}</td>
                  <td data-label="Type">
                    {d.doc_type
                      ? <span className="badge">{prettyDocType(d.doc_type)}</span>
                      : analyzing === d.id || analyzingNew
                        ? <span className="muted">reading…</span>
                        : <span className="muted">not read yet</span>}
                  </td>
                  <td data-label="What we found">
                    {deadlineCount > 0 && (
                      <span className="chip chip-warn">{deadlineCount} deadline{deadlineCount === 1 ? "" : "s"}</span>
                    )}
                    {flaggedCount > 0 && (
                      <span className="chip chip-danger">{flaggedCount} issue{flaggedCount === 1 ? "" : "s"}</span>
                    )}
                    {deadlineCount === 0 && flaggedCount === 0 && <span className="muted">, </span>}
                  </td>
                  <td data-label="Uploaded" className="muted-strong">{d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString() : ", "}</td>
                  <td className="actions">
                    <button
                      className="secondary"
                      onClick={() => openDoc(d.id)}
                      disabled={opening === d.id}
                    >
                      {opening === d.id ? "Opening…" : "Open"}
                    </button>{" "}
                    {d.gemini_analysis ? (
                      <button
                        className="secondary"
                        onClick={() => setSummaryFor(d)}
                        title="View the extracted summary"
                      >
                        Summary
                      </button>
                    ) : (
                      <button
                        className="secondary"
                        onClick={() => reanalyze(d.id)}
                        disabled={analyzing === d.id}
                        title="Read this document and extract deadlines and key details"
                      >
                        {analyzing === d.id ? "Reading…" : "Analyze"}
                      </button>
                    )}{" "}
                    <button className="secondary" onClick={() => setEditFor(d)}>Edit</button>{" "}
                    <button className="secondary" onClick={() => setDeleteFor(d)}>Delete</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <div className="no-print" style={{ marginTop: 24 }}>
        <button className="link-btn" onClick={toggleDeleted} aria-expanded={showDeleted}>
          {showDeleted ? "Hide recently deleted" : "Recently deleted"}
        </button>
        {showDeleted && (
          <div style={{ marginTop: 8 }}>
            <p className="muted-strong" style={{ fontSize: 13, marginTop: 0 }}>
              Deleted documents stay here for 30 days, so you can bring one back
              if you need it.
            </p>
            {deleted === null && !err && <Spinner />}
            {deleted && deleted.length === 0 && (
              <p className="muted-strong">Nothing has been deleted recently.</p>
            )}
            {deleted && deleted.length > 0 && (
              <table className="tbl tbl-cards">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Deleted</th>
                    <th>Time left</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {deleted.map((d) => (
                    <tr key={d.id}>
                      <td data-label="Name">{d.name}</td>
                      <td data-label="Deleted" className="muted-strong">
                        {deletedAt(d) ? new Date(deletedAt(d) as string).toLocaleDateString() : ", "}
                      </td>
                      <td data-label="Time left" className="muted-strong">
                        {daysLeftLabel(deletedAt(d))}
                      </td>
                      <td className="actions">
                        <button
                          className="secondary"
                          onClick={() => restore(d.id)}
                          disabled={restoring === d.id}
                        >
                          {restoring === d.id ? "Restoring…" : "Restore"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>

      <div className="row no-print" style={{ marginTop: 32 }}>
        <span className="spacer" />
        <Link to={inventoryHref}><button className="secondary">Inventory →</button></Link>
        <Link to={planHref} style={{ marginLeft: 8 }}>
          <button>See your plan →</button>
        </Link>
      </div>

      {summaryFor && (
        <SummaryModal
          doc={summaryFor}
          onClose={() => setSummaryFor(null)}
          onFixType={() => { setEditFor(summaryFor); setSummaryFor(null); }}
        />
      )}
      {editFor && (
        <EditDocModal
          doc={editFor}
          onClose={() => setEditFor(null)}
          onSaved={(typeChanged) => {
            const id = editFor.id;
            setEditFor(null);
            load();
            toast.show("Document updated.");
            // Changing the type clears the stored analysis server-side, so
            // re-run it automatically to keep the summary matching the
            // corrected type.
            if (typeChanged) reanalyze(id);
          }}
        />
      )}
      {deleteFor && (
        <ConfirmDialog
          title={`Delete "${deleteFor.name}"?`}
          body="This removes the file from your library. If you might need it for a claim, keep it, storage is no problem."
          confirmLabel="Delete document"
          onConfirm={confirmDelete}
          onCancel={() => setDeleteFor(null)}
        />
      )}
    </div>
  );
}

// Soft deletes carry a `deleted_at` timestamp that isn't on the base
// UserDocument type, so read it defensively.
function deletedAt(d: UserDocument): string | null {
  const v = (d as { deleted_at?: string | null }).deleted_at;
  return v ?? null;
}

// Deletes are kept for 30 days. Show roughly how long is left if we have a
// timestamp; otherwise say nothing specific.
function daysLeftLabel(deletedAtIso?: string | null): string {
  if (!deletedAtIso) return ", ";
  const deletedTime = new Date(deletedAtIso).getTime();
  if (Number.isNaN(deletedTime)) return ", ";
  const expires = deletedTime + 30 * 24 * 60 * 60 * 1000;
  const msLeft = expires - Date.now();
  const daysLeft = Math.ceil(msLeft / (24 * 60 * 60 * 1000));
  if (daysLeft <= 0) return "Expiring soon";
  return `${daysLeft} day${daysLeft === 1 ? "" : "s"} left`;
}

function prettyDocType(t: string): string {
  if (!t) return "";
  const known = DOC_TYPES.find((d) => d.value === t);
  return known ? known.label : t.replace(/_/g, " ");
}

// Misclassification shouldn't silently degrade the plan: users can correct
// the type (and fix the meaningless phone-scan filename) themselves.
function EditDocModal({
  doc,
  onClose,
  onSaved,
}: {
  doc: UserDocument;
  onClose: () => void;
  onSaved: (typeChanged: boolean) => void;
}) {
  const [name, setName] = useState(doc.name);
  const [docType, setDocType] = useState(doc.doc_type ?? "other");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const typeChanged = docType !== (doc.doc_type ?? "other");
    try {
      await api.updateDocument(doc.id, {
        name: name.trim() || doc.name,
        doc_type: docType,
      });
      onSaved(typeChanged);
    } catch (e: any) {
      setErr(e.message ?? String(e));
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} label="Edit document" maxWidth={460}>
      <h3 style={{ marginTop: 0 }}>Edit document</h3>
      <form onSubmit={save}>
        <label htmlFor="doc-name">Name</label>
        <input
          id="doc-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Home insurance policy 2026"
        />
        <label htmlFor="doc-type">
          What is this document?
        </label>
        <select id="doc-type" value={docType} onChange={(e) => setDocType(e.target.value)}>
          {DOC_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </select>
        <p className="muted-strong" style={{ fontSize: 13, marginTop: 6 }}>
          We guessed the type automatically. If we got it wrong, correcting it
          here makes sure the document counts toward your plan. Changing the
          type re-reads the document so the summary matches.
        </p>
        {err && <div className="error">{err}</div>}
        <div className="row" style={{ marginTop: 16 }}>
          <span className="spacer" />
          <button type="button" className="secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}

function SummaryModal({
  doc,
  onClose,
  onFixType,
}: {
  doc: UserDocument;
  onClose: () => void;
  onFixType: () => void;
}) {
  const analysis = doc.gemini_analysis;
  return (
    <Modal onClose={onClose} label={`Summary of ${doc.name}`}>
      <div className="row">
        <h2 style={{ margin: 0 }}>{doc.name}</h2>
        <span className="spacer" />
        <button className="ghost" onClick={onClose} aria-label="Close">×</button>
      </div>
      {doc.doc_type && (
        <p>
          <span className="badge">{prettyDocType(doc.doc_type)}</span>
        </p>
      )}
      {!analysis && <p className="muted-strong">No summary yet.</p>}
      {analysis && <AnalysisView analysis={analysis} />}
      {doc.doc_type === "other" && (
        <div className="notice" style={{ marginTop: 12 }}>
          This doesn't look like an insurance or disaster-recovery
          document, so we won't use it when generating your plan. It's still
          safely saved.{" "}
          <button className="link-btn" onClick={onFixType}>
            Did we get that wrong? Set the correct type.
          </button>
        </div>
      )}
    </Modal>
  );
}

// key_fields comes back as a list of {label, value} from the classifier, but
// older rows may have stored a plain object, handle both.
function keyFieldPairs(kf: GeminiAnalysis["key_fields"]): [string, string][] {
  if (Array.isArray(kf)) {
    return kf
      .filter((f) => f && (f.label || f.value))
      .map((f) => [f.label, f.value]);
  }
  if (kf && typeof kf === "object") {
    return Object.entries(kf).map(([k, v]) => [
      k,
      typeof v === "string" || typeof v === "number" ? String(v) : JSON.stringify(v),
    ]);
  }
  return [];
}

// coverage_limits can be a plain string (older stored analyses) or a
// CoverageLimit object. Normalize so the renderer always knows what it has.
function isCoverageLimitObject(c: string | CoverageLimit): c is CoverageLimit {
  return typeof c === "object" && c !== null && "text" in c;
}

function AnalysisView({ analysis }: { analysis: GeminiAnalysis }) {
  const fields = keyFieldPairs(analysis.key_fields);
  const rich: RichAnalysis = analysis.analysis ?? {};
  const summaryText = rich.plain_language_summary || analysis.summary;
  const deadlines = rich.deadlines ?? [];
  const flagged = rich.flagged_issues ?? [];
  const actions = rich.required_actions ?? [];
  const limits = rich.coverage_limits ?? [];
  const warnings = rich.warnings ?? [];
  const verification = rich.verification ?? null;
  const photoOnly = verification != null && verification.checked === false;

  return (
    <div style={{ marginTop: 12 }}>
      <DisclaimerBanner />

      {photoOnly && (
        <p className="photo-note">
          This came from a photo, so we could not check the quotes against the
          original text.
        </p>
      )}

      {summaryText && (
        <p style={{ marginTop: 0, fontSize: 15, lineHeight: 1.55 }}>{summaryText}</p>
      )}

      {flagged.length > 0 && (
        <Section title="Flagged issues">
          <ul className="summary-list">
            {flagged.map((f, i) => (
              <li key={i}>
                <span className="badge" style={{ marginRight: 8 }}>
                  {f.issue_type.replace(/_/g, " ").toLowerCase()}
                </span>
                {f.message}
                <SourceQuote quote={f.source_quote} page={f.page_number} verified={f.verified} />
              </li>
            ))}
          </ul>
        </Section>
      )}

      {deadlines.length > 0 && (
        <Section title="Deadlines">
          <ul className="summary-list">
            {deadlines.map((d, i) => (
              <li key={i}>
                <strong>{d.task}</strong> by {d.date}
                <SourceQuote quote={d.source_quote} page={d.page_number} verified={d.verified} />
              </li>
            ))}
          </ul>
          <p className="confirm-note">Confirm with your adjuster.</p>
        </Section>
      )}

      {actions.length > 0 && (
        <Section title="What you need to do">
          <ul className="summary-list">
            {actions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </Section>
      )}

      {(rich.deductible || (rich.coverage_scope && rich.coverage_scope.length > 0)) && (
        <p className="confirm-note" style={{ marginTop: 16 }}>
          Coverage details below are a summary. Confirm with your adjuster.
        </p>
      )}

      <DeductibleCard deductible={rich.deductible} />

      <CoverageScopeCard entries={rich.coverage_scope} />

      {limits.length > 0 && (
        <Section title="Coverage limits">
          <ul className="summary-list">
            {limits.map((c, i) => (
              <li key={i}>
                {isCoverageLimitObject(c) ? (
                  <>
                    {c.text}
                    <SourceQuote quote={c.source_quote} page={c.page_number} verified={c.verified} />
                  </>
                ) : (
                  c
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <GlossaryCard terms={rich.glossary} />

      {warnings.length > 0 && (
        <Section title="Heads up">
          <ul className="summary-list">
            {warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </Section>
      )}

      {fields.length > 0 && (
        <Section title="Key details">
          <table className="tbl">
            <thead>
              <tr><th>Field</th><th>Value</th></tr>
            </thead>
            <tbody>
              {fields.map(([k, v], i) => (
                <tr key={i}>
                  <td>{k.replace(/_/g, " ")}</td>
                  <td>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 16 }}>
      <h4 style={{ margin: "0 0 6px" }}>{title}</h4>
      {children}
    </div>
  );
}
