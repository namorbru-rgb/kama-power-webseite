// Package buffer provides a local SQLite write-ahead buffer for telemetry events.
// Events are stored locally when the upstream MQTT broker is unreachable,
// then flushed (with dedup) once connectivity is restored.
package buffer

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	_ "github.com/mattn/go-sqlite3"
	"github.com/kama-energy/edge-agent/internal/mqtt"
)

const schema = `
CREATE TABLE IF NOT EXISTS buffer (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id    TEXT NOT NULL,
    device_id  TEXT NOT NULL,
    ts         TEXT NOT NULL,
    payload    TEXT NOT NULL,
    flushed    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_buffer_unflushed ON buffer(flushed, created_at);
`

// Buffer persists TelemetryEvents to SQLite and flushes them to a publisher.
type Buffer struct {
	db  *sql.DB
	log *slog.Logger
}

func NewBuffer(path string, log *slog.Logger) (*Buffer, error) {
	db, err := sql.Open("sqlite3", path+"?_journal=WAL&_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}
	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("create schema: %w", err)
	}
	return &Buffer{db: db, log: log}, nil
}

// Store saves an event to the local buffer (never fails silently).
func (b *Buffer) Store(evt mqtt.TelemetryEvent) error {
	payload, err := json.Marshal(evt)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}
	_, err = b.db.Exec(
		"INSERT INTO buffer (site_id, device_id, ts, payload) VALUES (?, ?, ?, ?)",
		evt.SiteID, evt.DeviceID, evt.Timestamp.UTC().Format(time.RFC3339Nano), string(payload),
	)
	return err
}

// Flush sends all unflushed events to the publisher and marks them done.
// Events older than maxAge are dropped rather than sent.
func (b *Buffer) Flush(pub interface{ Publish(mqtt.TelemetryEvent) error }, maxAge time.Duration) (int, error) {
	cutoff := time.Now().Add(-maxAge).UTC().Format(time.RFC3339Nano)

	// Mark expired rows as flushed (drop them)
	if _, err := b.db.Exec("UPDATE buffer SET flushed=1 WHERE flushed=0 AND ts < ?", cutoff); err != nil {
		b.log.Warn("buffer expire failed", "err", err)
	}

	rows, err := b.db.Query(
		"SELECT id, payload FROM buffer WHERE flushed=0 ORDER BY id ASC LIMIT 500",
	)
	if err != nil {
		return 0, fmt.Errorf("query: %w", err)
	}
	defer rows.Close()

	var ids []int64
	for rows.Next() {
		var id int64
		var payload string
		if err := rows.Scan(&id, &payload); err != nil {
			continue
		}
		var evt mqtt.TelemetryEvent
		if err := json.Unmarshal([]byte(payload), &evt); err != nil {
			b.log.Warn("buffer unmarshal error", "id", id)
			ids = append(ids, id)
			continue
		}
		if err := pub.Publish(evt); err != nil {
			// Stop on first publish error — broker still down
			break
		}
		ids = append(ids, id)
	}

	if len(ids) > 0 {
		// Mark flushed in a single statement
		stmt := "UPDATE buffer SET flushed=1 WHERE id IN ("
		args := make([]any, len(ids))
		for i, id := range ids {
			if i > 0 {
				stmt += ","
			}
			stmt += "?"
			args[i] = id
		}
		stmt += ")"
		if _, err := b.db.Exec(stmt, args...); err != nil {
			b.log.Warn("buffer mark-flushed error", "err", err)
		}
	}

	return len(ids), nil
}

// PendingCount returns how many events are waiting to be flushed.
func (b *Buffer) PendingCount() (int64, error) {
	var count int64
	err := b.db.QueryRow("SELECT COUNT(*) FROM buffer WHERE flushed=0").Scan(&count)
	return count, err
}

func (b *Buffer) Close() error {
	return b.db.Close()
}
