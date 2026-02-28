#!/bin/bash
# Curl examples for PushPopActor REST API
#
# Prerequisites:
# - Docker Compose must be running: docker-compose up
# - API server should be accessible at http://localhost:8000

set -e

API_BASE="http://localhost:8000"
ACTOR_ID="my-test-queue"

echo "=== Dapr PushPopActor API Examples ==="
echo

# Health check
echo "1. Health Check"
echo "GET $API_BASE/health"
curl -s -X GET "$API_BASE/health" | jq '.'
echo
echo

# Push items
echo "2. Push Items to Queue"
echo "POST $API_BASE/queue/$ACTOR_ID/push"
echo

echo "Pushing item 1 (default priority 0)..."
curl -s -X POST "$API_BASE/queue/$ACTOR_ID/push" \
  -H "Content-Type: application/json" \
  -d '{
    "item": {
      "task_id": 1,
      "action": "send_email",
      "to": "user@example.com",
      "priority": "high"
    }
  }' | jq '.'
echo

echo "Pushing item 2 (default priority 0)..."
curl -s -X POST "$API_BASE/queue/$ACTOR_ID/push" \
  -H "Content-Type: application/json" \
  -d '{
    "item": {
      "task_id": 2,
      "action": "process_upload",
      "file": "document.pdf",
      "priority": "normal"
    }
  }' | jq '.'
echo

echo "Pushing item 3 (default priority 0)..."
curl -s -X POST "$API_BASE/queue/$ACTOR_ID/push" \
  -H "Content-Type: application/json" \
  -d '{
    "item": {
      "task_id": 3,
      "action": "generate_report",
      "report_type": "monthly",
      "priority": "low"
    }
  }' | jq '.'
echo
echo

# Pop single item
echo "3. Pop Single Item"
echo "POST $API_BASE/queue/$ACTOR_ID/pop"
curl -s -X POST "$API_BASE/queue/$ACTOR_ID/pop" | jq '.'
echo
echo

# Pop multiple items
echo "4. Pop Multiple Items"
echo "POST $API_BASE/queue/$ACTOR_ID/pop"
curl -s -X POST "$API_BASE/queue/$ACTOR_ID/pop" | jq '.'
echo
echo

# Pop from empty queue
echo "5. Pop from Empty Queue"
echo "POST $API_BASE/queue/$ACTOR_ID/pop"
curl -s -X POST "$API_BASE/queue/$ACTOR_ID/pop" | jq '.'
echo
echo

# Priority Queue Examples
echo "6. Priority Queue Examples"
echo "=========================================="
echo "The N-Queue Priority System allows items to be assigned to different priority levels."
echo "Lower priority index = higher priority (0 is highest)"
echo "Pop always drains lowest priority index first (0 → 1 → 2 → ...)"
echo
echo

PRIORITY_ACTOR="priority-demo"

echo "Pushing items with different priorities..."
echo

echo "Pushing high priority item (priority=0)..."
curl -s -X POST "$API_BASE/queue/$PRIORITY_ACTOR/push" \
  -H "Content-Type: application/json" \
  -d '{
    "item": {
      "task_id": 101,
      "action": "critical_alert",
      "message": "System outage detected"
    },
    "priority": 0
  }' | jq '.'
echo

echo "Pushing low priority item (priority=5)..."
curl -s -X POST "$API_BASE/queue/$PRIORITY_ACTOR/push" \
  -H "Content-Type: application/json" \
  -d '{
    "item": {
      "task_id": 102,
      "action": "cleanup_logs",
      "message": "Weekly cleanup task"
    },
    "priority": 5
  }' | jq '.'
echo

echo "Pushing medium priority item (priority=2)..."
curl -s -X POST "$API_BASE/queue/$PRIORITY_ACTOR/push" \
  -H "Content-Type: application/json" \
  -d '{
    "item": {
      "task_id": 103,
      "action": "send_report",
      "message": "Daily report generation"
    },
    "priority": 2
  }' | jq '.'
echo

echo "Pushing another high priority item (priority=0)..."
curl -s -X POST "$API_BASE/queue/$PRIORITY_ACTOR/push" \
  -H "Content-Type: application/json" \
  -d '{
    "item": {
      "task_id": 104,
      "action": "security_check",
      "message": "Suspicious activity"
    },
    "priority": 0
  }' | jq '.'
echo
echo

echo "Pop all items - notice priority 0 items returned first, then 2, then 5..."
echo "POST $API_BASE/queue/$PRIORITY_ACTOR/pop0"
curl -s -X POST "$API_BASE/queue/$PRIORITY_ACTOR/pop0" | jq '.'
echo
echo

echo "=== Examples Complete ==="
echo
echo "Tips:"
echo "  - Each actor ID maintains its own independent queues"
echo "  - Items are processed in FIFO order within each priority level"
echo "  - Priority 0 = highest priority (always dequeued first)"
echo "  - Pop drains priority 0 completely before moving to priority 1, etc."
echo "  - You can have multiple actor instances with different IDs"
echo "  - Pop returns a single item per call - loop to process multiple items"
echo "  - Priority levels are unbounded (0, 1, 2, ..., N)"
