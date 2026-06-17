package handlers

import (
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
)

type ProjectHandler struct {
	db *sql.DB
}

func NewProjectHandler(db *sql.DB) *ProjectHandler {
	return &ProjectHandler{db: db}
}

func (h *ProjectHandler) UpdateProject(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name string `json:"name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if req.Name == "" {
		http.Error(w, "name required", http.StatusUnprocessableEntity)
		return
	}
	row := h.db.QueryRow("SELECT owner_id FROM projects WHERE id = $1", r.URL.Query().Get("id"))
	var ownerID string
	if err := row.Scan(&ownerID); err == sql.ErrNoRows {
		http.Error(w, "not found", http.StatusNotFound)
		return
	} else if err != nil {
		log.Printf("db error: %v", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	if ownerID != r.Header.Get("X-User-ID") {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	if _, err := h.db.Exec("UPDATE projects SET name=$1 WHERE id=$2", req.Name, r.URL.Query().Get("id")); err != nil {
		log.Printf("update error: %v", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
