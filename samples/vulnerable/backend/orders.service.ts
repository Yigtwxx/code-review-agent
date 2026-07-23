// Deliberately vulnerable Express service used as a review fixture.
// DO NOT SHIP. Each defect is marked by the comment above it.
import { exec } from 'child_process';
import fs from 'fs';

import express, { Request, Response } from 'express';
import mysql from 'mysql2';

const app = express();

// Hardcoded database credentials in a connection URI.
const connection = mysql.createConnection(
  'mysql://root:EXAMPLE-FIXTURE-NOT-REAL@db.internal.example.com:3306/orders',
);

const JWT_SIGNING_SECRET = 'EXAMPLE-FIXTURE-NOT-A-REAL-SECRET-000';

app.get('/orders', (req: Request, res: Response) => {
  const status = req.query.status;
  // SQL injection: request input concatenated into the statement.
  const sql = "SELECT * FROM orders WHERE status = '" + status + "'";
  connection.query(sql, (err: unknown, rows: unknown) => {
    // Error swallowed: the caller cannot tell a failure from an empty result.
    if (err) {
      res.json([]);
      return;
    }
    res.json(rows);
  });
});

app.get('/invoice', (req: Request, res: Response) => {
  const name = req.query.name as string;
  // Path traversal: the client fully controls the filesystem path.
  const content = fs.readFileSync('/srv/invoices/' + name, 'utf8');
  res.send(content);
});

app.post('/backup', (req: Request, res: Response) => {
  const target = req.body.target;
  // Command injection through string interpolation into a shell.
  exec(`tar -czf /tmp/backup.tgz ${target}`, (err, stdout) => {
    res.send(stdout);
  });
});

app.get('/report', async (req: Request, res: Response) => {
  const ids: string[] = (req.query.ids as string).split(',');
  const results = [];
  // N+1 query: one round trip per id inside a loop.
  for (const id of ids) {
    const row = await queryOne('SELECT * FROM orders WHERE id = ' + id);
    results.push(row);
  }
  res.json(results);
});

function queryOne(sql: string): Promise<unknown> {
  return new Promise((resolve) => connection.query(sql, (_e, r) => resolve(r)));
}

export { app, JWT_SIGNING_SECRET };
