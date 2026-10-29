import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { api, errorMessage, fieldErrors } from "../api/client";
import AuthShell from "../components/AuthShell";
import { Notice, TextInput } from "../components/ui";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const uid = params.get("uid"), token = params.get("token");
  const [form, setForm] = useState({ password: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState({});

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setErrors({});
    if (form.password !== form.confirm) { setErrors({ confirm: "The passwords do not match." }); return; }
    setBusy(true);
    try { await api.post("/auth/password-reset/confirm/", { uid, token, new_password: form.password }); setDone(true); }
    catch (err) { setErrors(fieldErrors(err)); setError(errorMessage(err)); } finally { setBusy(false); }
  };

  const signIn = <Link className="font-medium text-brand-700 hover:underline" to="/login">Go to sign in</Link>;
  if (!uid || !token) {
    return <AuthShell title="Reset link problem" footer={<Link className="font-medium text-brand-700 hover:underline" to="/forgot-password">Request a new link</Link>}>
      <Notice tone="error">This reset link is incomplete. Open the link from your email again, or request a new one.</Notice></AuthShell>;
  }
  return (
    <AuthShell title="Choose a new password" footer={signIn}>
      {done ? <Notice tone="ok" title="Password updated">You can sign in with your new password now.</Notice> : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          {error && <Notice tone="error">{error}</Notice>}
          <TextInput label="New password" type="password" autoComplete="new-password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} error={errors.new_password} hint="At least 10 characters." />
          <TextInput label="Confirm new password" type="password" autoComplete="new-password" required value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} error={errors.confirm} />
          <button className="btn-primary w-full" disabled={busy || !form.password}>{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Update password</button>
        </form>
      )}
    </AuthShell>
  );
}
