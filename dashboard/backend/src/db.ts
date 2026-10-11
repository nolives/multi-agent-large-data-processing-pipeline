import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import pg from 'pg';

/** The one capability the routes need from a database: run a parameterized read query. */
export interface Db {
  query<T = Record<string, unknown>>(text: string, params?: unknown[]): Promise<{ rows: T[] }>;
}

/**
 * Loads DATABASE_URL from the repository's .env for local development. On Vercel the variable comes
 * from the project settings and this is a no-op. Existing environment values always win.
 */
export function loadEnv(): void {
  if (process.env.DATABASE_URL) return;
  const here = dirname(fileURLToPath(import.meta.url));
  for (const path of [join(here, '..', '..', '..', '.env'), join(here, '..', '..', '.env')]) {
    let raw: string;
    try {
      raw = readFileSync(path, 'utf8');
    } catch {
      continue;
    }
    for (const line of raw.split('\n')) {
      const eq = line.indexOf('=');
      if (eq === -1 || line.trimStart().startsWith('#')) continue;
      const key = line.slice(0, eq).trim();
      const value = line.slice(eq + 1).trim().replace(/^["']|["']$/g, '');
      if (key && value && process.env[key] === undefined) process.env[key] = value;
    }
  }
}

let pool: pg.Pool | undefined;

/** A small connection pool on the Neon pooled connection string. Created on first use. */
export function databaseFromEnv(): Db {
  return {
    async query<T>(text: string, params: unknown[] = []) {
      if (!pool) {
        loadEnv();
        const connectionString = process.env.DATABASE_URL;
        if (!connectionString) throw new Error('DATABASE_URL is not configured.');
        // Serverless functions are short-lived: keep the pool small and let idle connections go.
        pool = new pg.Pool({ connectionString, max: 3, idleTimeoutMillis: 10_000 });
      }
      const result = await pool.query(text, params);
      return { rows: result.rows as T[] };
    },
  };
}
