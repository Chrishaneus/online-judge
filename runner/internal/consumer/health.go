package consumer

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"
	"time"
)

// touchHealth records that the consumer is connected and consuming. The file
// is created once and never removed, so in a world-writable /tmp (sticky bit)
// sandboxed code can neither replace nor fake it.
func (c *Consumer) touchHealth() {
	if c.cfg.HealthFile == "" {
		return
	}
	now := time.Now()
	if err := os.WriteFile(c.cfg.HealthFile, []byte(now.UTC().Format(time.RFC3339)+"\n"), 0o644); err != nil {
		c.log.Warn("write health file", "path", c.cfg.HealthFile, "err", err)
	}
}

// CheckHealth reports whether the heartbeat file at path was written less
// than maxAge ago.
func CheckHealth(path string, maxAge time.Duration) error {
	fi, err := os.Stat(path)
	if err != nil {
		return err
	}
	if age := time.Since(fi.ModTime()); age >= maxAge {
		return fmt.Errorf("heartbeat is %s old (max %s)", age.Round(time.Second), maxAge)
	}
	return nil
}

// redact removes the password of rawURL from err's message.
func redact(err error, rawURL string) error {
	u, perr := url.Parse(rawURL)
	if perr != nil || u.User == nil {
		return err
	}
	pw, ok := u.User.Password()
	if !ok || pw == "" || !strings.Contains(err.Error(), pw) {
		return err
	}
	return errors.New(strings.ReplaceAll(err.Error(), pw, "xxxxx"))
}
