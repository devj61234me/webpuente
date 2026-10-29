import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 text-center">
      <p className="text-4xl font-semibold text-ink-900">404</p>
      <p className="mt-2 text-sm text-ink-500">This page does not exist.</p>
      <Link to="/dashboard" className="btn-primary mt-5">Go to the dashboard</Link>
    </div>
  );
}
