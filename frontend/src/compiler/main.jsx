import React from "react";
import { createRoot } from "react-dom/client";
import { initTheme } from "../shared/theme.js";
import App from "./App.jsx";
import "./styles/compiler.css";

initTheme({ floating: false, defaultTheme: "dark" });
createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
