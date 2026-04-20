// Package modbus polls Modbus TCP devices and converts readings to TelemetryEvents.
// Register maps are device-specific — see DeviceProfile definitions below.
package modbus

import (
	"fmt"
	"log/slog"
	"math"
	"time"

	"github.com/goburrow/modbus"
	"github.com/kama-energy/edge-agent/internal/mqtt"
)

// RegisterDef describes a single Modbus register to read.
type RegisterDef struct {
	Address  uint16
	Count    uint16
	Scale    float64 // multiply raw uint16 by this factor
	Field    string  // target TelemetryEvent field name
	UnitBase uint8   // Modbus unit ID
}

// DeviceProfile maps a device model to its register layout.
type DeviceProfile struct {
	Name      string
	Registers []RegisterDef
}

// SmartMeterProfile is a generic IEC 62056 / DIN EN 62056 smart meter layout.
// Adjust register addresses to match actual DSO meter model.
var SmartMeterProfile = DeviceProfile{
	Name: "generic_smart_meter",
	Registers: []RegisterDef{
		{Address: 0x0000, Count: 2, Scale: 0.1, Field: "power_w"},
		{Address: 0x0002, Count: 2, Scale: 0.01, Field: "energy_kwh"},
		{Address: 0x0004, Count: 1, Scale: 0.1, Field: "voltage_v"},
		{Address: 0x0006, Count: 1, Scale: 0.01, Field: "current_a"},
		{Address: 0x0008, Count: 1, Scale: 0.01, Field: "freq_hz"},
	},
}

// Poller polls a Modbus TCP device on a fixed interval.
type Poller struct {
	host     string
	port     int
	unitID   uint8
	interval time.Duration
	profile  DeviceProfile
	siteID   string
	deviceID string
	devType  string
	pub      interface{ Publish(mqtt.TelemetryEvent) error }
	log      *slog.Logger
}

type PollerConfig struct {
	Host     string
	Port     int
	UnitID   uint8
	Interval time.Duration
	Profile  DeviceProfile
	SiteID   string
	DeviceID string
	DevType  string
}

func NewPoller(cfg PollerConfig, pub interface{ Publish(mqtt.TelemetryEvent) error }, log *slog.Logger) *Poller {
	return &Poller{
		host:     cfg.Host,
		port:     cfg.Port,
		unitID:   cfg.UnitID,
		interval: cfg.Interval,
		profile:  cfg.Profile,
		siteID:   cfg.SiteID,
		deviceID: cfg.DeviceID,
		devType:  cfg.DevType,
		pub:      pub,
		log:      log,
	}
}

// Run blocks, polling the device every p.interval until ctx is cancelled.
func (p *Poller) Run(done <-chan struct{}) {
	ticker := time.NewTicker(p.interval)
	defer ticker.Stop()

	for {
		select {
		case <-done:
			return
		case <-ticker.C:
			if err := p.poll(); err != nil {
				p.log.Warn("modbus poll failed", "device", p.deviceID, "err", err)
			}
		}
	}
}

func (p *Poller) poll() error {
	handler := modbus.NewTCPClientHandler(fmt.Sprintf("%s:%d", p.host, p.port))
	handler.Timeout = 5 * time.Second
	handler.SlaveId = p.unitID

	if err := handler.Connect(); err != nil {
		return fmt.Errorf("connect: %w", err)
	}
	defer handler.Close()

	client := modbus.NewClient(handler)
	evt := mqtt.TelemetryEvent{
		SiteID:     p.siteID,
		DeviceID:   p.deviceID,
		DeviceType: p.devType,
		Timestamp:  time.Now().UTC(),
		Extra:      map[string]any{},
	}

	for _, reg := range p.profile.Registers {
		data, err := client.ReadHoldingRegisters(reg.Address, reg.Count)
		if err != nil {
			p.log.Warn("register read error", "address", reg.Address, "err", err)
			continue
		}
		val := parseRegisters(data, reg.Count) * reg.Scale
		if math.IsNaN(val) || math.IsInf(val, 0) {
			continue
		}
		switch reg.Field {
		case "power_w":
			evt.PowerW = &val
		case "energy_kwh":
			evt.EnergyKwh = &val
		case "voltage_v":
			evt.VoltageV = &val
		case "current_a":
			evt.CurrentA = &val
		case "freq_hz":
			evt.FreqHz = &val
		default:
			evt.Extra[reg.Field] = val
		}
	}

	return p.pub.Publish(evt)
}

func parseRegisters(data []byte, count uint16) float64 {
	if count == 1 && len(data) >= 2 {
		return float64(uint16(data[0])<<8 | uint16(data[1]))
	}
	if count == 2 && len(data) >= 4 {
		hi := uint32(data[0])<<8 | uint32(data[1])
		lo := uint32(data[2])<<8 | uint32(data[3])
		return float64(hi<<16 | lo)
	}
	return 0
}
