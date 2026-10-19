// Sits next to a disabled submit button and says exactly what is left to do.
// Each item jumps to the field when activated, so keyboard users can fix it fast.
export type MissingItem = { id: string; message: string };

export function MissingList({ items, id }: { items: MissingItem[]; id: string }) {
  if (items.length === 0) return null;
  return (
    <div id={id} className="missing-list" role="status" aria-live="polite">
      <p className="missing-title">
        {items.length === 1 ? "One thing left before you can continue:" : `${items.length} things left before you can continue:`}
      </p>
      <ul>
        {items.map((m) => (
          <li key={m.id}>
            <a
              href={`#${m.id}`}
              onClick={(e) => {
                e.preventDefault();
                const el = document.getElementById(m.id);
                if (el) { el.scrollIntoView({ block: "center" }); (el as HTMLElement).focus(); }
              }}
            >
              {m.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
