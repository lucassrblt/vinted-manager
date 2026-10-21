import { useEffect, useState } from "react";

export function useDebounce<T>(valeur: T, delai = 250): T {
  const [differee, setDifferee] = useState(valeur);
  useEffect(() => {
    const t = setTimeout(() => setDifferee(valeur), delai);
    return () => clearTimeout(t);
  }, [valeur, delai]);
  return differee;
}
