import { useEffect, useState } from "react";
import { api, AleExpense, AleCategory } from "../../api";
import { Modal, ConfirmDialog } from "../Modal";
import { Spinner } from "../Skeleton";
import { useToast } from "../Toast";
import "../../styles/claims.css";

const CATEGORY_LABELS: Record<AleCategory, string> = {
  hotel: "Hotel",
  meals: "Meals",
  transport: "Transport",
  storage: "Storage",
  pets: "Pets",
  cleanup: "Cleanup / contents retrieval",
  other: "Other",
};

// Plain-language "why this matters" for each reimbursable category, shown in
// the receipt checklist so people know what to keep and why an insurer pays it.
const CATEGORY_HINTS: Record<AleCategory, string> = {
  hotel: "Temporary lodging while you can't live at home. Keep every night's receipt.",
  meals: "The extra you spend on food above your normal grocery costs.",
  transport: "Fuel, taxis, or transit for the extra distance you now travel.",
  storage: "Storing belongings you salvaged while your home is repaired.",
  pets: "Boarding or care if your pets can't stay with you.",
  cleanup: "Retrieving or cleaning contents from the damaged home.",
  other: "Anything else your displacement is costing you.",
};

// The checklist surfaces the everyday categories first; "other" stays out of
// it (it's a catch-all, not a receipt to chase down).
const CHECKLIST_CATEGORIES: AleCategory[] = [
  "hotel", "meals", "transport", "storage", "pets", "cleanup",
];

// Inline, category-specific guidance shown under the receipt field, so the
// receipt a person uploads is one an insurer will actually accept.
const RECEIPT_TIPS: Record<AleCategory, string> = {
  hotel: "Use an itemized receipt showing a $0.00 balance, so it's clearly paid in full.",
  meals: "Keep the itemized receipt, not just the card slip. Insurers reimburse the extra over your normal grocery spend.",
  transport: "Note the trip's purpose on the receipt (e.g. commute from temporary lodging).",
  storage: "Keep the signed rental agreement or first invoice showing the monthly rate.",
  pets: "Ask the boarding facility for a dated invoice with your pet's name on it.",
  cleanup: "Get an itemized invoice listing the work done and the property address.",
  other: "Keep an itemized, dated receipt that shows what was paid and to whom.",
};

function formatMoney(amount: number): string {
  return amount.toLocaleString("en-CA", { style: "currency", currency: "CAD" });
}

function formatDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function toDateInput(iso?: string | null): string {
  const d = iso ? new Date(iso) : new Date();
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

type FormState = {
  category: AleCategory;
  amount: string;
  vendor: string;
  expense_date: string;
  notes: string;
  receipt_url: string;
};

function emptyForm(): FormState {
  return {
    category: "hotel",
    amount: "",
    vendor: "",
    expense_date: toDateInput(),
    notes: "",
    receipt_url: "",
  };
}

export default function AleTracker({ caseId }: { caseId: string }) {
  const toast = useToast();
  const [expenses, setExpenses] = useState<AleExpense[] | null>(null);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<AleExpense | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<AleExpense | null>(null);

  async function load() {
    setErr(null);
    try {
      const r = await api.listAleExpenses(caseId);
      const sorted = [...r.expenses].sort(
        (a, b) => new Date(b.expense_date ?? b.created_at ?? 0).getTime() - new Date(a.expense_date ?? a.created_at ?? 0).getTime(),
      );
      setExpenses(sorted);
      setTotal(r.total);
    } catch (e: any) {
      setErr(e.message ?? String(e));
      setExpenses([]);
    }
  }

  useEffect(() => { load(); }, [caseId]);

  function openAdd() {
    setEditing(null);
    setForm(emptyForm());
    setShowForm(true);
  }

  // Open the add form pre-set to one category, so logging a kind of receipt
  // straight from the checklist is a single tap, not a category hunt.
  function openAddCategory(category: AleCategory) {
    setEditing(null);
    setForm({ ...emptyForm(), category });
    setShowForm(true);
  }

  function openEdit(x: AleExpense) {
    setEditing(x);
    setForm({
      category: x.category,
      amount: String(x.amount),
      vendor: x.vendor ?? "",
      expense_date: toDateInput(x.expense_date),
      notes: x.notes ?? "",
      receipt_url: x.receipt_url ?? "",
    });
    setShowForm(true);
  }

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit() {
    const amount = Number(form.amount);
    if (!form.amount.trim() || isNaN(amount) || amount <= 0) {
      toast.show("Please enter an amount greater than zero.");
      return;
    }
    setSaving(true);
    const body: Partial<AleExpense> = {
      category: form.category,
      amount,
      vendor: form.vendor.trim() || null,
      expense_date: form.expense_date || null,
      notes: form.notes.trim() || null,
      receipt_url: form.receipt_url.trim() || null,
    };
    try {
      if (editing) {
        await api.updateAleExpense(editing.id, body);
        toast.show("Expense updated.");
      } else {
        await api.createAleExpense(caseId, body);
        toast.show("Expense saved.");
      }
      setShowForm(false);
      await load();
    } catch (e: any) {
      toast.show(e.message ?? "We couldn't save that. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function doDelete(x: AleExpense) {
    setConfirmDelete(null);
    try {
      await api.deleteAleExpense(x.id);
      toast.show("Expense removed.");
      await load();
    } catch (e: any) {
      toast.show(e.message ?? "We couldn't remove that. Please try again.");
    }
  }

  if (expenses === null) return <Spinner />;

  const loggedCategories = new Set(expenses.map((x) => x.category));

  return (
    <div>
      <p className="claim-intro">
        Keep every receipt for living costs while you are displaced. Organized
        receipts get additional living expenses reimbursed faster. Ask your
        insurer how to start your ALE claim.
      </p>

      <div className="ale-total">
        <div className="claim-entry-meta">Running total</div>
        <div className="amount">{formatMoney(total)}</div>
      </div>

      <div className="ale-checklist no-print">
        <h4>Receipts worth keeping</h4>
        <p className="claim-entry-meta" style={{ margin: "0 0 10px" }}>
          Log at least one of each that applies to you. You can add as many as
          you like, anytime.
        </p>
        <ul>
          {CHECKLIST_CATEGORIES.map((cat) => {
            const done = loggedCategories.has(cat);
            return (
              <li key={cat} className={done ? "done" : ""}>
                <span className="ale-check-mark" aria-hidden>{done ? "✓" : ""}</span>
                <div className="ale-check-body">
                  <strong>{CATEGORY_LABELS[cat]}</strong>
                  <span className="claim-entry-meta">{CATEGORY_HINTS[cat]}</span>
                </div>
                {done ? (
                  <span className="badge">Logged</span>
                ) : (
                  <button type="button" className="link-btn" onClick={() => openAddCategory(cat)}>
                    Add
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="row no-print" style={{ marginBottom: 14 }}>
        <button onClick={openAdd}>Add expense</button>
      </div>

      {err && <div className="error">{err}</div>}

      {expenses.length === 0 ? (
        <p className="muted-strong">
          No expenses logged yet. Add your first receipt to start tracking.
        </p>
      ) : (
        <div className="claim-list">
          {expenses.map((x) => (
            <div key={x.id} className="claim-entry">
              <div className="claim-entry-head">
                <strong>{formatMoney(x.amount)}</strong>
                <span className="badge">{CATEGORY_LABELS[x.category]}</span>
                {x.expense_date && <span className="claim-entry-meta">{formatDate(x.expense_date)}</span>}
              </div>
              {x.vendor && (
                <p className="claim-entry-meta" style={{ margin: "4px 0 0" }}>{x.vendor}</p>
              )}
              {x.notes && <p style={{ margin: "8px 0 0", fontSize: 15 }}>{x.notes}</p>}
              {x.receipt_url && (
                <p style={{ margin: "8px 0 0", fontSize: 14 }}>
                  <a href={x.receipt_url} target="_blank" rel="noreferrer">View receipt</a>
                </p>
              )}
              <div className="claim-entry-actions no-print">
                <button className="secondary" onClick={() => openEdit(x)}>Edit</button>
                <button className="secondary" onClick={() => setConfirmDelete(x)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <Modal onClose={() => setShowForm(false)} label={editing ? "Edit expense" : "Add expense"} maxWidth={520}>
          <h3 style={{ marginTop: 0 }}>{editing ? "Edit expense" : "Add expense"}</h3>

          <div className="grid grid-2" style={{ gap: 12 }}>
            <div>
              <label htmlFor="ale-category">Category</label>
              <select id="ale-category" value={form.category} onChange={(e) => set("category", e.target.value as AleCategory)}>
                <option value="hotel">Hotel</option>
                <option value="meals">Meals</option>
                <option value="transport">Transport</option>
                <option value="storage">Storage</option>
                <option value="pets">Pets</option>
                <option value="cleanup">Cleanup / contents retrieval</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label htmlFor="ale-amount">Amount (CAD)</label>
              <input
                id="ale-amount"
                type="number"
                min="0"
                step="0.01"
                value={form.amount}
                onChange={(e) => set("amount", e.target.value)}
                placeholder="0.00"
              />
              <p className="field-hint">
                Log the extra cost caused by being displaced, that's what ALE covers.
              </p>
            </div>
          </div>

          <div className="grid grid-2" style={{ gap: 12 }}>
            <div>
              <label htmlFor="ale-vendor">Vendor</label>
              <input
                id="ale-vendor"
                value={form.vendor}
                onChange={(e) => set("vendor", e.target.value)}
                placeholder="Where you paid"
              />
            </div>
            <div>
              <label htmlFor="ale-date">Date</label>
              <input
                id="ale-date"
                type="date"
                value={form.expense_date}
                onChange={(e) => set("expense_date", e.target.value)}
              />
            </div>
          </div>

          <label htmlFor="ale-notes">Notes (optional)</label>
          <textarea
            id="ale-notes"
            rows={2}
            value={form.notes}
            onChange={(e) => set("notes", e.target.value)}
            placeholder="Anything worth remembering"
          />

          <label htmlFor="ale-receipt">Receipt link (optional)</label>
          <input
            id="ale-receipt"
            value={form.receipt_url}
            onChange={(e) => set("receipt_url", e.target.value)}
            placeholder="https://..."
          />
          <p className="field-hint">{RECEIPT_TIPS[form.category]}</p>

          <div className="row" style={{ marginTop: 16 }}>
            <span className="spacer" />
            <button className="secondary" onClick={() => setShowForm(false)} disabled={saving}>Cancel</button>
            <button onClick={submit} disabled={saving}>{saving ? "Saving…" : "Save expense"}</button>
          </div>
        </Modal>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Remove this expense?"
          body="It will be removed from your expense list and the running total. You can add it again later."
          confirmLabel="Remove"
          onConfirm={() => doDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
