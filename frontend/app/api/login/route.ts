import { NextResponse } from 'next/server';
import { SESSION_COOKIE, validPassword } from '@/lib/auth';

export async function POST(request: Request) {
  const form = await request.formData();
  const password = String(form.get('password') ?? '');
  if (!validPassword(password)) {
    return NextResponse.redirect(new URL('/login?error=1', request.url), 303);
  }

  const response = NextResponse.redirect(new URL('/', request.url), 303);
  response.cookies.set(SESSION_COOKIE, process.env.CIVICFLOW_SESSION_SECRET as string, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 60 * 60 * 12,
  });
  return response;
}
