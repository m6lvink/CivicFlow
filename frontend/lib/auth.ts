export const SESSION_COOKIE = 'civicflow_session';

const sitePassword = process.env.CIVICFLOW_SITE_PASSWORD;
const sessionSecret = process.env.CIVICFLOW_SESSION_SECRET;

export function authRequired(): boolean {
  return Boolean(sitePassword || sessionSecret);
}

export function authReady(): boolean {
  return Boolean(sitePassword && sessionSecret);
}

export function validSession(value: string | undefined): boolean {
  if (!authRequired()) return true;
  return authReady() && value === sessionSecret;
}

export function validPassword(value: string): boolean {
  return authReady() && value === sitePassword;
}
