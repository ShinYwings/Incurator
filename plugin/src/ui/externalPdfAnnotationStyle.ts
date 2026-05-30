export interface ZoteroAnnotationBoxStyle {
  border: string;
  borderBottom?: string;
  backgroundColor: string;
  boxShadow?: string;
  opacity?: string;
  mixBlendMode?: string;
}

export function buildZoteroAnnotationBoxStyle(type?: string, color?: string): ZoteroAnnotationBoxStyle {
  const stroke = color || "#ffff00";
  
  if (type === "highlight") {
    return {
      border: "none",
      backgroundColor: stroke,
      opacity: "0.4",
      mixBlendMode: "multiply",
    };
  } else if (type === "underline") {
    return {
      border: "none",
      borderBottom: `2px solid ${stroke}`,
      backgroundColor: "transparent",
    };
  } else if (type === "image") {
    return {
      border: `2px dashed ${stroke}`,
      backgroundColor: "transparent",
    };
  } else {
    return {
      border: `2px solid ${stroke}`,
      backgroundColor: "transparent",
      boxShadow: "0 0 0 1px rgba(0, 0, 0, 0.18)",
    };
  }
}
