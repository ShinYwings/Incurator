export interface ZoteroAnnotationBoxStyle {
  border: string;
  backgroundColor: string;
  boxShadow: string;
}

export function buildZoteroAnnotationBoxStyle(color?: string): ZoteroAnnotationBoxStyle {
  const stroke = color || "#ffff00";
  return {
    border: `2px solid ${stroke}`,
    backgroundColor: "transparent",
    boxShadow: "0 0 0 1px rgba(0, 0, 0, 0.18)",
  };
}
