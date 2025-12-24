#!/bin/bash

echo "🛑 Stoppe Container..."
docker-compose down --remove-orphans

echo "✅ Container gestoppt!"
