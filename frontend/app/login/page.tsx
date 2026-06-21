import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { authReady, validSession, SESSION_COOKIE } from '@/lib/auth';

type Props = {
  searchParams: Promise<{ error?: string }>;
};

export default async function LoginPage({ searchParams }: Props) {
  const cookieStore = await cookies();
  if (validSession(cookieStore.get(SESSION_COOKIE)?.value)) {
    redirect('/');
  }

  const { error } = await searchParams;
  const misconfigured = !authReady();

  return (
    <main className="min-h-screen bg-cream flex items-center justify-center px-6 py-12">
      <section className="w-full max-w-sm rounded-lg border border-border bg-surface p-6">
        <p className="text-xs uppercase tracking-wide text-subtle">Private demo</p>
        <h1 className="mt-2 font-serif text-2xl font-semibold text-ink">CivicFlow</h1>
        <p className="mt-2 text-sm text-muted">
          Enter the site password to use the permit advisor.
        </p>

        <form action="/api/login" method="post" className="mt-6 space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-ink">Password</span>
            <input
              type="password"
              name="password"
              required
              autoFocus
              className="mt-1 w-full rounded border border-border bg-off-white px-3 py-2 text-ink"
            />
          </label>

          {misconfigured && (
            <p className="text-sm text-fail-text">
              Login is not configured. Set CIVICFLOW_SITE_PASSWORD and CIVICFLOW_SESSION_SECRET.
            </p>
          )}

          {error && !misconfigured && (
            <p className="text-sm text-fail-text">Wrong password.</p>
          )}

          <button
            type="submit"
            disabled={misconfigured}
            className="w-full rounded bg-primary px-4 py-2.5 font-semibold text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
          >
            Log in
          </button>
        </form>
      </section>
    </main>
  );
}
