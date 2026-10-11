-- bookings.db schema (web-srv, D:\emberline\data\bookings.db)
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS class_sessions (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    starts_utc  TEXT NOT NULL,
    seats       INTEGER NOT NULL,
    price_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    session_id   INTEGER NOT NULL REFERENCES class_sessions(id),
    status       TEXT NOT NULL DEFAULT 'held',   -- held, paid, cancelled, void
    hold_expires_utc TEXT,
    reminder_sent INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY,
    booking_id      INTEGER NOT NULL REFERENCES bookings(id),
    amount_cents    INTEGER NOT NULL,
    provider_ref    TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refunds (
    id           INTEGER PRIMARY KEY,
    payment_id   INTEGER NOT NULL REFERENCES payments(id),
    amount_cents INTEGER NOT NULL,
    reason       TEXT NOT NULL,
    approved_by  TEXT NOT NULL,
    status       TEXT NOT NULL,                  -- pending, succeeded, failed
    created_utc  TEXT NOT NULL
);
