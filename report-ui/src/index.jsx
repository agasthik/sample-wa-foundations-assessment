import "@cloudscape-design/global-styles/index.css";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";

// The Python report generator embeds the assessment result as JSON in this
// element; the bundle itself never fetches anything over the network.
const dataElement = document.getElementById("wafa-report-data");
const data = JSON.parse(dataElement.textContent);

createRoot(document.getElementById("wafa-report-root")).render(<App data={data} />);
