import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { PaymentProvider } from "./payment-flow";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PaymentProvider>
      <App />
    </PaymentProvider>
  </StrictMode>,
);
