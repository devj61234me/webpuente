import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { errorMessage, fieldErrors } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import AuthShell from "../components/AuthShell";
import { Notice, TextInput } from "../components/ui";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ first_name: "", last_name: "", email: "", password: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState({});
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setErrors({});
    if (form.password !== form.confirm) { setErrors({ confirm: "The passwords do not match." }); return; }
    setBusy(true);
    try {
      await register({ email: form.email.trim(), password: form.password, first_name: form.first_name.trim(), last_name: form.last_name.trim() });
      navigate("/dashboard", { replace: true });
    } catch (err) { setErrors(fieldErrors(err)); setError(errorMessage(err)); } finally { setBusy(false); }
  };

  return (
    <AuthShell title="Create your account" subtitle="Plan your website redirects in one place." footer={<>Already have an account? <Link className="font-medium text-brand-700 hover:underline" to="/login">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="grid grid-cols-2 gap-3">
          <TextInput label="First name" autoComplete="given-name" value={form.first_name} onChange={set("first_name")} error={errors.first_name} />
          <TextInput label="Last name" autoComplete="family-name" value={form.last_name} onChange={set("last_name")} error={errors.last_name} />
        </div>
        <TextInput label="Email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} error={errors.email} />
        <TextInput label="Password" type="password" autoComplete="new-password" required value={form.password} onChange={set("password")} error={errors.password} hint="At least 10 characters. Avoid common passwords." />
        <TextInput label="Confirm password" type="password" autoComplete="new-password" required value={form.confirm} onChange={set("confirm")} error={errors.confirm} />
        <button className="btn-primary w-full" disabled={busy || !form.email || !form.password}>{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Create account</button>
      </form>
    </AuthShell>
  );
}
