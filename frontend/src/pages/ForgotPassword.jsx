import { useState } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { api, errorMessage } from "../api/client";
import AuthShell from "../components/AuthShell";
import { Notice, TextInput } from "../components/ui";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try { await api.post("/auth/password-reset/", { email: email.trim() }); setDone(true); }
    catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  };

  return (
    <AuthShell title="Reset your password" subtitle="We will email you a link if an account exists for this address." footer={<Link className="font-medium text-brand-700 hover:underline" to="/login">Back to sign in</Link>}>
      {done ? (
        <Notice tone="ok" title="Check your inbox">If an account exists for that email, a reset link has been sent. The link works for one hour. Check your spam folder too.</Notice>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          {error && <Notice tone="error">{error}</Notice>}
          <TextInput label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <button className="btn-primary w-full" disabled={busy || !email}>{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Send reset link</button>
        </form>
      )}
    </AuthShell>
  );
}
