-- D1: the queryable half of the site.
--
-- Deliberately NOT the content. Posts stay markdown in git; this holds the
-- datasets that sit behind a visualisation, where shipping the whole thing as
-- a JSON file would be the wrong shape.

CREATE TABLE IF NOT EXISTS datasets (
  name        TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  rows        INTEGER NOT NULL DEFAULT 0,
  updated     TEXT NOT NULL            -- ISO date, authored, never a clock
);

CREATE TABLE IF NOT EXISTS series (
  dataset TEXT NOT NULL REFERENCES datasets(name) ON DELETE CASCADE,
  t       TEXT NOT NULL,               -- ISO timestamp or ordinal
  key     TEXT NOT NULL,               -- which line/facet this point belongs to
  value   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS series_lookup ON series(dataset, t);
CREATE INDEX IF NOT EXISTS series_key    ON series(dataset, key);
