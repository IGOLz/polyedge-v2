import { Pool } from "pg";

const {
  POSTGRES_USER,
  POSTGRES_PASSWORD,
  POSTGRES_DB,
  POSTGRES_HOST,
  POSTGRES_PORT,
} = process.env;

const pool = new Pool({
  user: POSTGRES_USER,
  password: POSTGRES_PASSWORD,
  database: POSTGRES_DB,
  host: POSTGRES_HOST,
  port: POSTGRES_PORT ? Number(POSTGRES_PORT) : 5432,
  max: 5,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});

export async function query<T extends Record<string, unknown>>(
  text: string,
  params?: (string | number | boolean | null)[]
): Promise<T[]> {
  const client = await pool.connect();
  try {
    await client.query("SET statement_timeout = '5000'");
    const result = await client.query(text, params);
    return result.rows as T[];
  } finally {
    client.release();
  }
}
