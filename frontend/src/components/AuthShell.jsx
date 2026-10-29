import { Logo } from "./Layout";

export default function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center text-ink-900">
          <Logo />
          <p className="mt-1 text-sm text-ink-500">Migrate Smarter. Redirect with Confidence.</p>
        </div>
        <div className="card p-6">
          <h1 className="text-lg font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
          <div className="mt-5">{children}</div>
        </div>
        {footer && <p className="mt-4 text-center text-sm text-ink-500">{footer}</p>}
      </div>
    </div>
  );
}
