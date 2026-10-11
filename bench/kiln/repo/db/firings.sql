-- firings.db schema (studio-srv, D:\emberline\data\firings.db)
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS kilns (
    id      TEXT PRIMARY KEY,           -- k1, k2, k3
    model   TEXT NOT NULL,
    zones   INTEGER NOT NULL,
    link    TEXT NOT NULL               -- COM3, COM4 or host:port
);

INSERT OR IGNORE INTO kilns VALUES ('k1', 'Fictional ProFire 5', 1, 'COM3');
INSERT OR IGNORE INTO kilns VALUES ('k2', 'Fictional ProFire 7', 3, 'COM4');
INSERT OR IGNORE INTO kilns VALUES ('k3', 'Fictional ProFire 7', 3, 'k3-ctl:502');

CREATE TABLE IF NOT EXISTS firings (
    id          INTEGER PRIMARY KEY,
    kiln_id     TEXT NOT NULL REFERENCES kilns(id),
    profile     TEXT NOT NULL,
    started_utc TEXT NOT NULL,
    ended_utc   TEXT,
    outcome     TEXT                    -- complete, aborted, fault
);

CREATE TABLE IF NOT EXISTS readings (
    firing_id  INTEGER NOT NULL REFERENCES firings(id),
    ts_utc     TEXT NOT NULL,
    zone       INTEGER NOT NULL,
    temp_c     REAL NOT NULL,
    setpoint_c REAL
);

CREATE INDEX IF NOT EXISTS idx_readings_firing ON readings(firing_id, ts_utc);
