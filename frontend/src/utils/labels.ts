/** Human-readable labels for backend enum values. */

const SPECIAL: Record<string, string> = {
  wc: "WC",
  ensuite: "En-suite",
  kitchen_dining: "Kitchen and dining",
  open_plan_living: "Open-plan living",
  floor_to_ceiling: "Floor to ceiling",
  detached_house: "Detached house",
  semi_detached_house: "Semi-detached house",
  traditional_british: "Traditional British",
  victorian_inspired: "Victorian-inspired",
};

export function label(value: string): string {
  if (SPECIAL[value]) return SPECIAL[value];
  const words = value.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const FLOOR_NAMES = ["Ground floor", "First floor", "Second floor", "Third floor"];

export function floorName(level: number): string {
  return FLOOR_NAMES[level] ?? `Floor ${level}`;
}

export function metres(value: number): string {
  return `${Number(value.toFixed(2))} m`;
}
