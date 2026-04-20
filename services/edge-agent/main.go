// KAMA Edge Agent — collects device telemetry and forwards to the EMQX broker.
//
// Supported protocols (Phase 1):
//   - MQTT 5 pass-through (devices that already publish MQTT)
//   - Modbus TCP polling (meters, older inverters)
//
// On connectivity loss, events are buffered locally in SQLite and replayed
// once the broker is reachable again (max 24h buffer).
package main

import (
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"gopkg.in/yaml.v3"

	"github.com/kama-energy/edge-agent/internal/buffer"
	"github.com/kama-energy/edge-agent/internal/modbus"
	"github.com/kama-energy/edge-agent/internal/mqtt"
)

type Config struct {
	SiteID    string       `yaml:"siteId"`
	Broker    BrokerConfig `yaml:"broker"`
	Devices   []DeviceCfg  `yaml:"devices"`
	BufferDB  string       `yaml:"bufferDb"`
}

type BrokerConfig struct {
	URL      string `yaml:"url"`
	ClientID string `yaml:"clientId"`
	Username string `yaml:"username"`
	Password string `yaml:"password"`
}

type DeviceCfg struct {
	ID       string `yaml:"id"`
	Name     string `yaml:"name"`
	Type     string `yaml:"type"`     // solar_inverter | bess | grid_meter | smart_meter
	Protocol string `yaml:"protocol"` // modbus_tcp | mqtt_passthrough | solarman_v5
	Host     string `yaml:"host"`
	Port     int    `yaml:"port"`
	UnitID   uint8  `yaml:"unitId"`
	Interval int    `yaml:"intervalSec"` // polling interval for Modbus
}

func main() {
	cfgPath := flag.String("config", "/etc/kama-edge/config.yaml", "Path to config file")
	flag.Parse()

	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	data, err := os.ReadFile(*cfgPath)
	if err != nil {
		log.Error("failed to read config", "path", *cfgPath, "err", err)
		os.Exit(1)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		log.Error("failed to parse config", "err", err)
		os.Exit(1)
	}

	// ── Local buffer ─────────────────────────────────────────────────────────
	dbPath := cfg.BufferDB
	if dbPath == "" {
		dbPath = "/var/lib/kama-edge/buffer.db"
	}
	buf, err := buffer.NewBuffer(dbPath, log)
	if err != nil {
		log.Error("failed to open buffer", "err", err)
		os.Exit(1)
	}
	defer buf.Close()

	// ── MQTT publisher ────────────────────────────────────────────────────────
	pub, err := mqtt.NewPublisher(mqtt.Config{
		BrokerURL: cfg.Broker.URL,
		ClientID:  cfg.Broker.ClientID,
		Username:  cfg.Broker.Username,
		Password:  cfg.Broker.Password,
	}, log)
	if err != nil {
		log.Warn("broker not reachable at startup — buffering locally", "err", err)
	}

	// Buffered publisher: stores locally if pub is nil or publish fails
	bufPub := &bufferedPublisher{pub: pub, buf: buf, log: log}

	// ── Background flush ──────────────────────────────────────────────────────
	done := make(chan struct{})
	go func() {
		ticker := time.NewTicker(30 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				if pending, _ := buf.PendingCount(); pending > 0 {
					flushed, err := buf.Flush(pub, 24*time.Hour)
					if err != nil {
						log.Warn("flush error", "err", err)
					} else if flushed > 0 {
						log.Info("flushed buffered events", "count", flushed)
					}
				}
			}
		}
	}()

	// ── Start device pollers ──────────────────────────────────────────────────
	for _, dev := range cfg.Devices {
		d := dev
		switch d.Protocol {
		case "modbus_tcp":
			interval := time.Duration(d.Interval) * time.Second
			if interval == 0 {
				interval = 60 * time.Second
			}
			poller := modbus.NewPoller(modbus.PollerConfig{
				Host:     d.Host,
				Port:     d.Port,
				UnitID:   d.UnitID,
				Interval: interval,
				Profile:  modbus.SmartMeterProfile, // TODO: select profile by d.Type/model
				SiteID:   cfg.SiteID,
				DeviceID: d.ID,
				DevType:  d.Type,
			}, bufPub, log)
			go poller.Run(done)
			log.Info("started modbus poller", "device", d.ID, "host", d.Host)

		case "mqtt_passthrough":
			// Devices that already publish MQTT: edge agent subscribes and re-publishes normalized
			log.Info("mqtt_passthrough configured — adapter pending device specs", "device", d.ID)

		case "solarman_v5":
			// SolarmanV5 TCP protocol for DEYE/Solis inverters — adapter pending
			log.Info("solarman_v5 adapter pending hardware specs", "device", d.ID)

		default:
			log.Warn("unknown protocol", "device", d.ID, "protocol", d.Protocol)
		}
	}

	log.Info("KAMA edge agent running", "site", cfg.SiteID)

	// ── Graceful shutdown ─────────────────────────────────────────────────────
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	close(done)
	if pub != nil {
		pub.Close()
	}
	log.Info("edge agent stopped")
}

// bufferedPublisher wraps the MQTT publisher with local SQLite fallback.
type bufferedPublisher struct {
	pub interface {
		Publish(mqtt.TelemetryEvent) error
		Close()
	}
	buf *buffer.Buffer
	log *slog.Logger
}

func (b *bufferedPublisher) Publish(evt mqtt.TelemetryEvent) error {
	if b.pub != nil {
		if err := b.pub.Publish(evt); err == nil {
			return nil
		}
	}
	return b.buf.Store(evt)
}
