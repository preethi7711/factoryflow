// Original, hand-drawn SVG illustrations (no stock photos). One small picture per kind of item, chosen
// from the item's code or name, so new items get a sensible picture without new code. Pictures are
// decoration: aria-hidden, the name is always written next to them.

const C = {
  tur: "#E8A317",
  tur3: "#F2C25A",
  tur7: "#9A6608",
  choc: "#3B2416",
  choc5: "#6B5242",
  cream: "#FFF6E3",
  chilli: "#C8361D",
  leaf: "#2F6B3A",
};

function Murukku() {
  // A murukku is one coiled rope of dough: drawn as a spiral of half-circles, with ridges on top.
  const spiral =
    "M32 32 m-3 0 a3 3 0 1 1 6 0 a7 7 0 1 1 -14 0 a11 11 0 1 1 22 0 a15 15 0 1 1 -30 0 a19 19 0 1 1 38 0";
  return (
    <>
      <path d={spiral} fill="none" stroke={C.tur7} strokeWidth="6" strokeLinecap="round" />
      <path
        d={spiral}
        fill="none"
        stroke={C.tur3}
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray="2 3"
      />
    </>
  );
}

function Mixture() {
  return (
    <>
      <path d="M8 30h48a24 22 0 0 1-48 0z" fill={C.choc5} />
      {[
        [18, 26],
        [26, 22],
        [34, 25],
        [42, 21],
        [48, 27],
        [22, 30],
        [38, 30],
      ].map(([x, y], i) => (
        <circle
          key={i}
          cx={x}
          cy={y}
          r="3.2"
          fill={i % 3 === 0 ? C.chilli : i % 3 === 1 ? C.tur : C.leaf}
        />
      ))}
      <path
        d="M14 24c6-4 10 2 16-2s10 2 18-2"
        stroke={C.tur3}
        strokeWidth="2.5"
        fill="none"
        strokeLinecap="round"
      />
    </>
  );
}

function Chips() {
  return [
    [22, 34],
    [36, 28],
    [42, 40],
    [26, 44],
  ].map(([x, y], i) => (
    <g key={i}>
      <circle cx={x} cy={y} r="11" fill={C.tur3} stroke={C.tur7} strokeWidth="2" />
      <circle cx={x} cy={y} r="5" fill="none" stroke={C.tur} strokeWidth="1.5" />
    </g>
  ));
}

function Sweet() {
  return (
    <>
      <rect x="12" y="20" width="40" height="26" rx="4" fill={C.tur} />
      <path d="M12 30h40M25 20v26M39 20v26" stroke={C.tur7} strokeWidth="1.5" />
      <rect x="12" y="20" width="40" height="6" rx="3" fill={C.tur3} />
    </>
  );
}

function Flour() {
  return (
    <>
      <path
        d="M18 18h28l4 34a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4z"
        fill={C.cream}
        stroke={C.choc5}
        strokeWidth="2"
      />
      <path d="M18 18c4-6 24-6 28 0" fill="none" stroke={C.choc5} strokeWidth="2" />
      <path d="M24 34c4-6 12-6 16 0-4 6-12 6-16 0z" fill={C.tur3} />
    </>
  );
}

function Oil() {
  return (
    <>
      <rect
        x="16"
        y="20"
        width="32"
        height="36"
        rx="5"
        fill={C.tur}
        stroke={C.tur7}
        strokeWidth="2"
      />
      <rect x="26" y="10" width="12" height="10" rx="2" fill={C.leaf} />
      <path d="M32 30c-4 6-5 9-5 11a5 5 0 0 0 10 0c0-2-1-5-5-11z" fill={C.cream} />
    </>
  );
}

function Spice() {
  return (
    <>
      <rect x="18" y="22" width="28" height="32" rx="6" fill={C.chilli} />
      <rect x="20" y="14" width="24" height="9" rx="3" fill={C.choc} />
      <rect x="22" y="32" width="20" height="12" rx="2" fill={C.cream} />
    </>
  );
}

function Pouch() {
  // The zigzag top is the heat-sealed edge of a snack pouch.
  return (
    <>
      <path
        d="M16 14l4 4 4-4 4 4 4-4 4 4 4-4 4 4 4-4v36a6 6 0 0 1-6 6H22a6 6 0 0 1-6-6z"
        fill={C.tur}
        stroke={C.tur7}
        strokeWidth="2"
      />
      <circle cx="32" cy="36" r="8" fill={C.cream} />
      <path d="M28 36a4 4 0 1 1 8 0" fill="none" stroke={C.tur7} strokeWidth="2" />
    </>
  );
}

function Carton() {
  return (
    <>
      <path
        d="M10 24l22-10 22 10v26L32 60 10 50z"
        fill="#C89B6D"
        stroke={C.choc5}
        strokeWidth="2"
      />
      <path d="M10 24l22 10 22-10M32 34v26" fill="none" stroke={C.choc5} strokeWidth="2" />
    </>
  );
}

function Sack() {
  return (
    <rect
      x="14"
      y="16"
      width="36"
      height="38"
      rx="8"
      fill={C.cream}
      stroke={C.choc5}
      strokeWidth="2"
    />
  );
}

const RULES = [
  [/MURUKKU/i, Murukku],
  [/MIXTURE/i, Mixture],
  [/CHIP/i, Chips],
  [/PAK|SWEET|LADDU|BURFI/i, Sweet],
  [/FLOUR|ATTA|MAIDA|RICE/i, Flour],
  [/OIL/i, Oil],
  [/SPICE|SALT|CHILLI|MASALA/i, Spice],
  [/POUCH/i, Pouch],
  [/CARTON|BOX/i, Carton],
];

function artFor(text = "") {
  return (RULES.find(([re]) => re.test(text)) || [null, Sack])[1];
}

export default function ItemArt({ code = "", name = "", className = "h-10 w-10" }) {
  const Art = artFor(`${code} ${name}`);
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true" focusable="false">
      <Art />
    </svg>
  );
}

// The brand mark: a single murukku coil.
export function Logo({ className = "h-8 w-8" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true" focusable="false">
      <circle cx="32" cy="32" r="30" fill={C.tur} />
      <path
        d="M32 32 m-3 0 a3 3 0 1 1 6 0 a7 7 0 1 1 -14 0 a11 11 0 1 1 22 0 a15 15 0 1 1 -30 0"
        fill="none"
        stroke={C.choc}
        strokeWidth="4.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
