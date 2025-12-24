#!/bin/bash

echo "🛑 Stoppe Container..."
./stop.sh

echo "🔨 Baue und starte Container..."
docker-compose up --build -d

echo "✅ Container gestartet!"
echo "📝 Logs anzeigen mit: ./logs.sh"
