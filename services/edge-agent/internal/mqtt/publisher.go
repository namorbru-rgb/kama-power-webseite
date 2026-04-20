// Package mqtt handles publishing normalized telemetry to the EMQX broker.
package mqtt

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"log/slog"
	"time"

	paho "github.com/eclipse/paho.mqtt.golang"
)

// TelemetryEvent is the canonical normalized message published upstream.
type TelemetryEvent struct {
	SiteID     string             `json:"siteId"`
	DeviceID   string             `json:"deviceId"`
	DeviceType string             `json:"deviceType"`
	Timestamp  time.Time          `json:"timestamp"`
	PowerW     *float64           `json:"powerW,omitempty"`
	EnergyKwh  *float64           `json:"energyKwh,omitempty"`
	VoltageV   *float64           `json:"voltageV,omitempty"`
	CurrentA   *float64           `json:"currentA,omitempty"`
	FreqHz     *float64           `json:"freqHz,omitempty"`
	Direction  string             `json:"direction"`
	SocPct     *float64           `json:"socPct,omitempty"`
	Extra      map[string]any     `json:"extra,omitempty"`
}

// Publisher sends TelemetryEvents to EMQX over MQTT.
type Publisher struct {
	client paho.Client
	topic  string
	log    *slog.Logger
}

type Config struct {
	BrokerURL  string // e.g. "tls://broker.kama.energy:8883"
	ClientID   string
	Username   string
	Password   string
	Topic      string // e.g. "kama/telemetry/{siteId}/{deviceId}"
	TLSConfig  *tls.Config
}

func NewPublisher(cfg Config, log *slog.Logger) (*Publisher, error) {
	opts := paho.NewClientOptions().
		AddBroker(cfg.BrokerURL).
		SetClientID(cfg.ClientID).
		SetUsername(cfg.Username).
		SetPassword(cfg.Password).
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(5 * time.Second).
		SetKeepAlive(30 * time.Second)

	if cfg.TLSConfig != nil {
		opts.SetTLSConfig(cfg.TLSConfig)
	}

	client := paho.NewClient(opts)
	token := client.Connect()
	if token.WaitTimeout(15*time.Second) && token.Error() != nil {
		return nil, fmt.Errorf("mqtt connect: %w", token.Error())
	}

	return &Publisher{client: client, topic: cfg.Topic, log: log}, nil
}

// Publish serializes and sends a TelemetryEvent. Non-blocking with QoS 1.
func (p *Publisher) Publish(evt TelemetryEvent) error {
	topic := fmt.Sprintf("kama/telemetry/%s/%s", evt.SiteID, evt.DeviceID)
	payload, err := json.Marshal(evt)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}

	token := p.client.Publish(topic, 1, false, payload)
	if token.WaitTimeout(5*time.Second) && token.Error() != nil {
		return fmt.Errorf("mqtt publish: %w", token.Error())
	}

	p.log.Debug("published telemetry", "topic", topic, "bytes", len(payload))
	return nil
}

func (p *Publisher) Close() {
	p.client.Disconnect(500)
}
