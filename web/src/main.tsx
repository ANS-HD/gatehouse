import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./app/App";
import { AppProviders } from "./app/AppProviders";
import "./styles/index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders><App /></AppProviders>
  </StrictMode>,
);
