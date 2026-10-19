import { Link } from "react-router-dom";

// Shown beside every upload that is sent to Google Gemini, so the disclosure is
// visible at the moment of the action, not only in the policy.
export function AiNotice({ kind }: { kind: "photo" | "document" }) {
  return (
    <p className="field-help" style={{ marginTop: 10 }}>
      {kind === "photo" ? "Photos" : "Documents"} you add here are sent to Google's Gemini service to be
      analyzed, and Google's servers may be outside Canada. AI results can be wrong, so check them before
      relying on them. <Link to="/legal/privacy" target="_blank" rel="noopener">How we handle your data</Link>.
    </p>
  );
}
