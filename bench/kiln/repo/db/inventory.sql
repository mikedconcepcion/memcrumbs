-- inventory.db schema (studio-srv, D:\emberline\data\inventory.db)
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS glazes (
    id           INTEGER PRIMARY KEY,
    supplier_sku TEXT NOT NULL,
    name         TEXT NOT NULL,
    cone_min     INTEGER,
    cone_max     INTEGER,
    stock_kg     REAL NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'active'   -- active, void
);

-- Added after the 2026-09-14 duplicate-row incident.
CREATE UNIQUE INDEX IF NOT EXISTS idx_glazes_sku ON glazes(supplier_sku);

CREATE TABLE IF NOT EXISTS clay_stock (
    id       INTEGER PRIMARY KEY,
    body     TEXT NOT NULL,
    bags     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_orders (
    id          INTEGER PRIMARY KEY,
    supplier    TEXT NOT NULL,
    ordered_utc TEXT NOT NULL,
    arrived_utc TEXT
);
