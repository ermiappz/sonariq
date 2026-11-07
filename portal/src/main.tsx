import React from "react";
import ReactDOM from "react-dom/client";
import "@design/sonariq.css"; // design tokens and components, used as is
import "./index.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
