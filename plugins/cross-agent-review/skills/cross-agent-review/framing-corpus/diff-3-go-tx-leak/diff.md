// services/orders/sync.go (new file)
package orders

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type Order struct {
	ID     string  `json:"id"`
	Total  float64 `json:"total"`
	Status string  `json:"status"`
}

func SyncOrderToWarehouse(
	ctx context.Context,
	db *sql.DB,
	httpClient *http.Client,
	order Order,
) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}

	_, err = tx.ExecContext(ctx,
		"UPDATE orders SET sync_status = $1, sync_started_at = $2 WHERE id = $3",
		"pending", time.Now(), order.ID,
	)
	if err != nil {
		return fmt.Errorf("mark pending: %w", err)
	}

	body, err := json.Marshal(order)
	if err != nil {
		return fmt.Errorf("marshal order: %w", err)
	}

	req, err := http.NewRequestWithContext(
		ctx, "POST", "https://warehouse.example.com/orders", bytes.NewReader(body),
	)
	if err != nil {
		return fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("warehouse request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return fmt.Errorf("warehouse returned %d", resp.StatusCode)
	}

	_, err = tx.ExecContext(ctx,
		"UPDATE orders SET sync_status = $1, sync_completed_at = $2 WHERE id = $3",
		"synced", time.Now(), order.ID,
	)
	if err != nil {
		return fmt.Errorf("mark synced: %w", err)
	}

	return tx.Commit()
}
