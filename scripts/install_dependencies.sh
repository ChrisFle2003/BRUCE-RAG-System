#!/bin/bash
echo "Installing PostgreSQL dependencies..."
apt-get update
apt-get install -y postgresql postgresql-contrib postgresql-server-dev-all

echo "Installing pgvector..."
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
make install
