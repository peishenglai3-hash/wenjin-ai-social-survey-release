import { useContext } from "react";
import { AppCtx } from "../context/contextValue";

export function useApp() {
  return useContext(AppCtx);
}
