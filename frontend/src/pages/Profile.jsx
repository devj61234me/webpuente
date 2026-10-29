import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { toast } from "react-toastify";
import { api, errorMessage, fieldErrors } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { fmtDate } from "../lib/format";
import { Card, ConfirmDialog, Notice, PageHeader, TextInput } from "../components/ui";

export default function Profile() {
  const { user, setUser, logoutAll, acceptTokens } = useAuth();
  const navigate = useNavigate();
  const [names, setNames] = useState({ first_name: user.first_name || "", last_name: user.last_name || "" });
  const [pw, setPw] = useState({ current_password: "", new_password: "", confirm: "" });
  const [pwErrors, setPwErrors] = useState({});
  const [busy, setBusy] = useState("");
  const [del, setDel] = useState({ open: false, password: "", error: "" });

  const saveProfile = async (e) => {
    e.preventDefault(); setBusy("profile");
    try { const { data } = await api.patch("/auth/me/", names); setUser(data); toast.success("Profile saved."); }
    catch (err) { toast.error(errorMessage(err)); } finally { setBusy(""); }
  };
  const changePassword = async (e) => {
    e.preventDefault(); setPwErrors({});
    if (pw.new_password !== pw.confirm) { setPwErrors({ confirm: "The passwords do not match." }); return; }
    setBusy("password");
    try {
      const { data } = await api.post("/auth/change-password/", { current_password: pw.current_password, new_password: pw.new_password });
      acceptTokens(data); // other devices are signed out; this session continues
      setPw({ current_password: "", new_password: "", confirm: "" });
      toast.success("Password changed. Other devices were signed out.");
    } catch (err) { setPwErrors(fieldErrors(err)); if (!Object.keys(fieldErrors(err)).length) toast.error(errorMessage(err)); } finally { setBusy(""); }
  };
  const deleteAccount = async () => {
    setBusy("delete"); setDel((d) => ({ ...d, error: "" }));
    try {
      await api.delete("/auth/me/", { data: { password: del.password } });
      await logoutAll().catch(() => {});
      navigate("/login");
    } catch (err) { setDel((d) => ({ ...d, error: errorMessage(err) })); } finally { setBusy(""); }
  };

  return (
    <>
      <PageHeader title="Profile" subtitle={`${user.email} · member since ${fmtDate(user.date_joined)}`} />
      <div className="grid max-w-4xl gap-6">
        <Card title="Your details">
          <form onSubmit={saveProfile} className="grid gap-4 sm:grid-cols-2">
            <TextInput label="First name" value={names.first_name} onChange={(e) => setNames({ ...names, first_name: e.target.value })} maxLength={60} />
            <TextInput label="Last name" value={names.last_name} onChange={(e) => setNames({ ...names, last_name: e.target.value })} maxLength={60} />
            <div className="sm:col-span-2"><button className="btn-primary" disabled={busy === "profile"}>{busy === "profile" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Save</button></div>
          </form>
        </Card>
        <Card title="Change password">
          <form onSubmit={changePassword} className="grid gap-4 sm:max-w-md">
            <TextInput label="Current password" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} error={pwErrors.current_password} />
            <TextInput label="New password" type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} error={pwErrors.new_password} hint="At least 10 characters." />
            <TextInput label="Confirm new password" type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} error={pwErrors.confirm} />
            <div><button className="btn-primary" disabled={busy === "password" || !pw.current_password || !pw.new_password}>{busy === "password" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}Change password</button></div>
          </form>
        </Card>
        <Card title="Sessions">
          <p className="mb-3 text-sm text-ink-500">Sign out of WebPuente on every device where you are signed in.</p>
          <button className="btn-secondary" onClick={async () => { await logoutAll(); navigate("/login"); }}>Sign out everywhere</button>
        </Card>
        <Card title="Delete account">
          <p className="mb-3 text-sm text-ink-500">Permanently deletes your account, projects, URLs, decisions and exports. This cannot be undone.</p>
          <button className="btn-danger" onClick={() => setDel({ open: true, password: "", error: "" })}>Delete my account…</button>
        </Card>
      </div>
      <ConfirmDialog open={del.open} danger title="Delete your account?" confirmLabel="Delete everything" busy={busy === "delete"} disabled={!del.password}
        onClose={() => setDel({ open: false, password: "", error: "" })} onConfirm={deleteAccount}>
        <p>All of your projects and data will be removed permanently. Enter your password to confirm.</p>
        {del.error && <Notice tone="error">{del.error}</Notice>}
        <TextInput label="Password" type="password" autoComplete="current-password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} />
      </ConfirmDialog>
    </>
  );
}
