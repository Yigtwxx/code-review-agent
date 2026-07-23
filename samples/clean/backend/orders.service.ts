// Hardened counterpart of samples/vulnerable/backend/orders.service.ts.
import { execFile } from 'node:child_process';
import path from 'node:path';

import express, { Request, Response } from 'express';
import mysql from 'mysql2/promise';

const app = express();

// Connection details come from the environment, never from source.
const pool = mysql.createPool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
});

const INVOICE_ROOT = path.resolve('/srv/invoices');
const ALLOWED_STATUSES = new Set(['pending', 'paid', 'cancelled']);

app.get('/orders', async (req: Request, res: Response) => {
  const status = String(req.query.status ?? '');
  if (!ALLOWED_STATUSES.has(status)) {
    res.status(400).json({ error: 'Unknown status' });
    return;
  }
  try {
    // Placeholders keep the value out of the statement text.
    const [rows] = await pool.query('SELECT * FROM orders WHERE status = ?', [status]);
    res.json(rows);
  } catch (cause) {
    // Failures surface rather than being reported as an empty result.
    req.log?.error({ cause }, 'order lookup failed');
    res.status(500).json({ error: 'Order lookup failed' });
  }
});

app.get('/invoice', async (req: Request, res: Response) => {
  const name = path.basename(String(req.query.name ?? ''));
  const target = path.resolve(INVOICE_ROOT, name);
  if (!target.startsWith(`${INVOICE_ROOT}${path.sep}`)) {
    res.status(400).json({ error: 'Invalid invoice name' });
    return;
  }
  res.sendFile(target);
});

app.post('/backup', (req: Request, res: Response) => {
  const target = path.basename(String(req.body?.target ?? ''));
  // No shell: arguments are passed as a fixed list.
  execFile('tar', ['-czf', '/tmp/backup.tgz', target], (cause, stdout) => {
    if (cause) {
      res.status(500).json({ error: 'Backup failed' });
      return;
    }
    res.send(stdout);
  });
});

app.get('/report', async (req: Request, res: Response) => {
  const ids = String(req.query.ids ?? '')
    .split(',')
    .filter((id) => /^\d+$/.test(id));
  if (ids.length === 0) {
    res.json([]);
    return;
  }
  // One round trip instead of one per id.
  const placeholders = ids.map(() => '?').join(',');
  const [rows] = await pool.query(
    `SELECT * FROM orders WHERE id IN (${placeholders})`,
    ids,
  );
  res.json(rows);
});

export { app };
