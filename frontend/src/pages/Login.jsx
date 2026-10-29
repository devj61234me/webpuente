import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import AuthShell from "../components/AuthShell";
import { Notice, TextInput } from "../components/ui";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await login(form.email.trim(), form.password);
      navigate(location.state?.from || "/dashboard", { replace: true });
    } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  };

  return (
    <AuthShell title="Sign in" subtitle="Welcome back." footer={<>New to WebPuente? <Link className="font-medium text-brand-700 hover:underline" to="/register">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <TextInput label="Email" type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <TextInput label="Password" type="password" autoComplete="current-password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <button className="btn-primary w-full" disabled={busy || !form.email || !form.password}>{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Sign in</button>
        <p className="text-center text-sm"><Link className="text-brand-700 hover:underline" to="/forgot-password">Forgot your password?</Link></p>
      </form>
    </AuthShell>
  );
}
