#!/bin/bash
echo "Initializing PostgreSQL schema..."
psql -U bruce -d bruce_rag < schema/00_knowledge_db.sql
psql -U bruce -d bruce_rag < schema/01_finish_db.sql
echo "Database initialized!"
