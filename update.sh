#!/bin/bash
# update.sh — Safe update script for PolyEdge
#
# This script updates analysis + trading WITHOUT touching core.
# Core keeps running 24/7 uninterrupted.
#
# Usage:
#   ./update.sh           # Update analysis + trading
#   ./update.sh trading   # Update only trading
#   ./update.sh analysis  # Update only analysis
#   ./update.sh all       # Update everything INCLUDING core (rare!)

set -e

SERVICES="${1:-analysis trading}"

if [ "$1" = "all" ]; then
    echo "⚠️  WARNING: This will restart ALL services including CORE!"
    echo "   Core will be offline during the rebuild."
    read -p "   Are you sure? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
    SERVICES="core analysis trading"
fi

echo "🔄 Pulling latest code..."
git pull

echo "🔨 Building: $SERVICES"
docker compose build $SERVICES

echo "🚀 Restarting: $SERVICES"
docker compose up -d $SERVICES

echo ""
echo "✅ Update complete!"
echo ""

# Show status
docker compose ps
