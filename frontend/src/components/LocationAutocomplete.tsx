import { useEffect, useRef, useState } from "react";

const ALBERTA = [
  "Medicine Hat, AB", "Cypress County, AB", "Bow Island, AB", "Lethbridge, AB",
  "Taber, AB", "Warner, AB", "Vulcan, AB", "Pincher Creek, AB", "Cardston, AB",
  "Willow Creek, AB", "Acadia, AB", "Drumheller, AB", "Kneehill, AB", "Starland, AB",
  "Wheatland, AB", "Calgary, AB", "Airdrie, AB", "Chestermere, AB", "Foothills, AB",
  "Stettler, AB", "Wainwright, AB", "Provost, AB", "Vermilion River, AB", "Red Deer, AB",
  "Lacombe, AB", "Sylvan Lake, AB", "Ponoka, AB", "Rocky Mountain House, AB",
  "Clearwater County, AB", "Camrose, AB", "Leduc, AB", "Wetaskiwin, AB", "Beaver County, AB",
  "Edmonton, AB", "Sherwood Park, AB", "St. Albert, AB", "Spruce Grove, AB", "Cold Lake, AB",
  "Bonnyville, AB", "St. Paul, AB", "Athabasca, AB", "Westlock, AB", "Barrhead, AB",
  "Thorhild, AB", "Edson, AB", "Hinton, AB", "Yellowhead County, AB", "Banff, AB",
  "Canmore, AB", "Kananaskis, AB", "Jasper, AB", "Wood Buffalo, AB", "Fort McMurray, AB",
  "Fort Chipewyan, AB", "Slave Lake, AB", "High Prairie, AB", "Lesser Slave River, AB",
  "Grande Cache, AB", "Valleyview, AB", "Greenview, AB", "Grande Prairie, AB",
  "Peace River, AB", "Fairview, AB",
];

type Props = {
  value: string;
  onChange: (v: string) => void;
  id?: string;
  required?: boolean;
};

export function LocationAutocomplete({ value, onChange, id = "location-input", required }: Props) {
  const listId = `${id}-list`;
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const query = value.trim().toLowerCase();
  const matches = query
    ? ALBERTA.filter((l) => l.toLowerCase().includes(query)).slice(0, 8)
    : ALBERTA.slice(0, 8);

  const inAlberta = ALBERTA.some((l) => l.toLowerCase() === value.trim().toLowerCase());
  const outOfArea = value.trim().length >= 3 && !inAlberta && matches.length === 0;

  function pick(item: string) {
    onChange(item);
    setOpen(false);
  }

  return (
    <div className="autocomplete" ref={wrapRef}>
      <input
        id={id}
        type="text"
        role="combobox"
        aria-controls={listId}
        aria-activedescendant={open && matches[activeIdx] ? `${id}-opt-${activeIdx}` : undefined}
        aria-required={required || undefined}
        required={required}
        value={value}
        placeholder="Start typing your city or town…"
        autoComplete="off"
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActiveIdx(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (!open) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setActiveIdx((i) => Math.min(i + 1, matches.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActiveIdx((i) => Math.max(i - 1, 0)); }
          else if (e.key === "Enter" && matches[activeIdx]) { e.preventDefault(); pick(matches[activeIdx]); }
          else if (e.key === "Escape") setOpen(false);
        }}
        aria-autocomplete="list"
        aria-expanded={open}
      />
      {open && matches.length > 0 && (
        <div className="autocomplete-list" id={listId} role="listbox">
          {matches.map((m, i) => (
            <div
              key={m}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === activeIdx}
              className={`autocomplete-item${i === activeIdx ? " active" : ""}`}
              onMouseDown={(e) => { e.preventDefault(); pick(m); }}
              onMouseEnter={() => setActiveIdx(i)}
            >
              {m}
            </div>
          ))}
        </div>
      )}
      {outOfArea && (
        <div className="notice" style={{ marginTop: 10 }}>
          <strong>We don't cover {value.trim()} yet.</strong>
          <span className="muted-strong" style={{ display: "block", marginTop: 4 }}>
            Right now Rebuildr is built for Alberta, Canada. You can still create a case , 
            documents and inventory will work, but local recommendations may not match your area.
            Try entering the closest Alberta town, or continue with what you typed.
          </span>
        </div>
      )}
    </div>
  );
}
