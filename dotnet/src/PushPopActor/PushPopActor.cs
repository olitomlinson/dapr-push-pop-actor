using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Dapr.Actors;
using Dapr.Actors.Runtime;
using Microsoft.Extensions.Logging;
using PushPopActor.Interfaces;

namespace PushPopActor;

/// <summary>
/// PushPopActor - A FIFO queue-based Dapr actor with priority support.
/// Implements segmented storage (100 items per segment) for scalable queue operations.
/// </summary>
public class PushPopActor : Actor, IPushPopActor
{
    private const int MaxSegmentSize = 100;
    private const int MinLockTtlSeconds = 1;
    private const int MaxLockTtlSeconds = 300;
    private const int DefaultLockTtlSeconds = 30;
    private const int LockIdLength = 11;

    public PushPopActor(ActorHost host) : base(host)
    {
    }

    /// <summary>
    /// Push an item to the queue with optional priority.
    /// </summary>
    public async Task<PushResponse> Push(PushRequest request)
    {
        try
        {
            // Validate input
            if (string.IsNullOrEmpty(request.ItemJson))
            {
                Logger.LogWarning("Push failed: ItemJson is empty");
                return new PushResponse { Success = false };
            }

            // Validate priority >= 0
            if (request.Priority < 0)
            {
                Logger.LogWarning($"Push failed: priority must be >= 0, got {request.Priority}");
                return new PushResponse { Success = false };
            }

            // Parse item JSON to validate and convert to dictionary
            Dictionary<string, object> itemDict;
            try
            {
                itemDict = JsonSerializer.Deserialize<Dictionary<string, object>>(request.ItemJson)
                    ?? new Dictionary<string, object>();
            }
            catch (JsonException ex)
            {
                Logger.LogWarning($"Push failed: invalid JSON - {ex.Message}");
                return new PushResponse { Success = false };
            }

            int priority = request.Priority;

            // Get metadata
            var metadata = await GetMetadataAsync();

            // Ensure priority queue exists in metadata
            if (!metadata.ContainsKey("queues"))
            {
                metadata["queues"] = new Dictionary<string, object>();
            }

            // Handle JsonElement for queues dictionary
            var queuesObj = metadata["queues"];
            Dictionary<string, object>? queues = null;
            if (queuesObj is JsonElement queuesJsonElement)
            {
                queues = JsonSerializer.Deserialize<Dictionary<string, object>>(queuesJsonElement.GetRawText());
            }
            else if (queuesObj is Dictionary<string, object> dict)
            {
                queues = dict;
            }
            queues ??= new Dictionary<string, object>();

            string priorityKey = priority.ToString();
            if (!queues.ContainsKey(priorityKey))
            {
                queues[priorityKey] = new Dictionary<string, object>
                {
                    ["head_segment"] = 0,
                    ["tail_segment"] = 0,
                    ["count"] = 0
                };
            }
            metadata["queues"] = queues;

            // Handle JsonElement for queue metadata
            var queueMetaObj = queues[priorityKey];
            Dictionary<string, object>? queueMeta = null;
            if (queueMetaObj is JsonElement queueJsonElement)
            {
                queueMeta = JsonSerializer.Deserialize<Dictionary<string, object>>(queueJsonElement.GetRawText());
            }
            else if (queueMetaObj is Dictionary<string, object> dict)
            {
                queueMeta = dict;
            }
            queueMeta ??= new Dictionary<string, object>();

            int tailSegment = GetIntValue(queueMeta["tail_segment"]);
            int headSegment = GetIntValue(queueMeta["head_segment"]);
            int count = GetIntValue(queueMeta["count"]);

            // Get current tail segment
            string segmentKey = $"queue_{priority}_seg_{tailSegment}";
            var segment = await StateManager.TryGetStateAsync<List<Dictionary<string, object>>>(segmentKey);
            var segmentList = segment.HasValue ? segment.Value : new List<Dictionary<string, object>>();

            // Check if segment is full BEFORE appending (matching Python)
            if (segmentList.Count >= MaxSegmentSize)
            {
                // Allocate new segment
                tailSegment++;
                segmentKey = $"queue_{priority}_seg_{tailSegment}";
                segmentList = new List<Dictionary<string, object>>();
            }

            // Append item to segment (FIFO)
            segmentList.Add(itemDict);

            // Update metadata (count and pointers)
            count++;
            queueMeta["head_segment"] = headSegment;
            queueMeta["tail_segment"] = tailSegment;
            queueMeta["count"] = count;
            queues[priorityKey] = queueMeta;
            metadata["queues"] = queues;

            // Save segment and metadata
            await StateManager.SetStateAsync(segmentKey, segmentList);

            await SaveMetadataAsync(metadata);
            await StateManager.SaveStateAsync();

            Logger.LogInformation($"Pushed item to queue at priority {priority}, count now {count}");
            return new PushResponse { Success = true };
        }
        catch (Exception ex)
        {
            Logger.LogError(ex, "Error in PushAsync");
            return new PushResponse { Success = false };
        }
    }

    /// <summary>
    /// Pop a single item from the queue (FIFO, lowest priority first).
    /// </summary>
    public async Task<PopResponse> Pop()
    {
        try
        {
            // Check if queue is locked
            var lockState = await StateManager.TryGetStateAsync<Dictionary<string, object>>("_active_lock");
            if (lockState.HasValue)
            {
                var lockData = lockState.Value;
                double expiresAt = Convert.ToDouble(lockData["expires_at"]);
                double now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

                if (now < expiresAt)
                {
                    Logger.LogInformation("Queue is locked, cannot pop");
                    return new PopResponse { ItemsJson = new List<string>() };
                }
                else
                {
                    // Lock expired - return items and clear lock
                    await HandleExpiredLockAsync(lockData);
                }
            }

            var metadata = await GetMetadataAsync();

            if (!metadata.ContainsKey("queues"))
            {
                return new PopResponse { ItemsJson = new List<string>() };
            }

            // Handle both Dictionary<string, object> and JsonElement for queues
            var queuesObj = metadata["queues"];
            Dictionary<string, object>? queues = null;

            if (queuesObj is JsonElement jsonElement)
            {
                queues = JsonSerializer.Deserialize<Dictionary<string, object>>(jsonElement.GetRawText());
            }
            else if (queuesObj is Dictionary<string, object> dict)
            {
                queues = dict;
            }

            if (queues == null || queues.Count == 0)
            {
                return new PopResponse { ItemsJson = new List<string>() };
            }

            // Find lowest priority with items
            var sortedPriorities = queues.Keys
                .Select(k => int.Parse(k))
                .OrderBy(p => p)
                .ToList();

            foreach (var priority in sortedPriorities)
            {
                // Handle both Dictionary<string, object> and JsonElement
                var queueMetaObj = queues[priority.ToString()];
                Dictionary<string, object>? queueMeta = null;

                if (queueMetaObj is JsonElement queueJsonElement)
                {
                    queueMeta = JsonSerializer.Deserialize<Dictionary<string, object>>(queueJsonElement.GetRawText());
                }
                else if (queueMetaObj is Dictionary<string, object> dict)
                {
                    queueMeta = dict;
                }

                if (queueMeta == null) continue;

                // Handle JsonElement for numeric values
                int count = GetIntValue(queueMeta["count"]);
                if (count == 0) continue;

                int headSegment = GetIntValue(queueMeta["head_segment"]);
                int tailSegment = GetIntValue(queueMeta["tail_segment"]);

                // Get head segment
                string segmentKey = $"queue_{priority}_seg_{headSegment}";
                var segment = await StateManager.TryGetStateAsync<List<Dictionary<string, object>>>(segmentKey);

                if (!segment.HasValue || segment.Value.Count == 0)
                {
                    // Defensive: fix count desync
                    Logger.LogWarning($"Count desync detected for priority {priority}, removing queue metadata");
                    queues.Remove(priority.ToString());
                    metadata["queues"] = queues;
                    await SaveMetadataAsync(metadata);
                    await StateManager.SaveStateAsync();
                    continue;
                }

                // Pop single item from front (FIFO)
                var segmentList = segment.Value;
                var item = segmentList[0];
                segmentList.RemoveAt(0);

                // Handle segment cleanup
                if (segmentList.Count == 0)
                {
                    if (headSegment < tailSegment)
                    {
                        // More segments exist, move to next
                        // Delete the empty segment from state
                        await StateManager.RemoveStateAsync(segmentKey);
                        headSegment++;
                        // Update metadata pointers
                        count--;
                        queueMeta["head_segment"] = headSegment;
                        queueMeta["tail_segment"] = tailSegment;
                        queueMeta["count"] = count;
                        queues[priority.ToString()] = queueMeta;
                        metadata["queues"] = queues;
                        await SaveMetadataAsync(metadata);
                        await StateManager.SaveStateAsync();

                        Logger.LogInformation($"Popped item from priority {priority}, count now {count}");

                        // Serialize item to JSON
                        var itemJson = JsonSerializer.Serialize(item);
                        return new PopResponse { ItemsJson = new List<string> { itemJson } };
                    }
                    else
                    {
                        // Last segment empty, queue is now empty
                        // Delete the segment from state
                        await StateManager.RemoveStateAsync(segmentKey);
                        // Delete queue metadata
                        queues.Remove(priority.ToString());
                        metadata["queues"] = queues;
                        await SaveMetadataAsync(metadata);
                        await StateManager.SaveStateAsync();

                        Logger.LogInformation($"Popped last item from priority {priority}, queue now empty");

                        // Serialize item to JSON
                        var itemJson = JsonSerializer.Serialize(item);
                        return new PopResponse { ItemsJson = new List<string> { itemJson } };
                    }
                }
                else
                {
                    // Segment still has items, save it
                    await StateManager.SetStateAsync(segmentKey, segmentList);
                    count--;
                    queueMeta["head_segment"] = headSegment;
                    queueMeta["tail_segment"] = tailSegment;
                    queueMeta["count"] = count;
                    queues[priority.ToString()] = queueMeta;
                    metadata["queues"] = queues;
                    await SaveMetadataAsync(metadata);
                    await StateManager.SaveStateAsync();

                    Logger.LogInformation($"Popped item from priority {priority}, count now {count}");

                    // Serialize item to JSON
                    var itemJson = JsonSerializer.Serialize(item);
                    return new PopResponse { ItemsJson = new List<string> { itemJson } };
                }
            }

            return new PopResponse { ItemsJson = new List<string>() };
        }
        catch (Exception ex)
        {
            Logger.LogError(ex, "Error in PopAsync");
            return new PopResponse { ItemsJson = new List<string>() };
        }
    }

    // Helper methods follow in next section...

    private async Task<Dictionary<string, object>> GetMetadataAsync()
    {
        var result = await StateManager.TryGetStateAsync<Dictionary<string, object>>("metadata");
        if (result.HasValue)
        {
            return result.Value;
        }

        return new Dictionary<string, object>
        {
            ["queues"] = new Dictionary<string, object>()
        };
    }

    private async Task SaveMetadataAsync(Dictionary<string, object> metadata)
    {
        await StateManager.SetStateAsync("metadata", metadata);
    }

    private async Task HandleExpiredLockAsync(Dictionary<string, object> lockData)
    {
        // Return items to queue and clear lock
        Logger.LogInformation("Lock expired, returning items to queue");

        if (lockData.ContainsKey("items_json"))
        {
            var itemsJson = lockData["items_json"] as List<object>;
            if (itemsJson != null)
            {
                foreach (var itemJson in itemsJson)
                {
                    if (itemJson is string jsonString)
                    {
                        await Push(new PushRequest
                        {
                            ItemJson = jsonString,
                            Priority = 0
                        });
                    }
                }
            }
        }

        await StateManager.RemoveStateAsync("_active_lock");
        await StateManager.SaveStateAsync();
    }

    /// <summary>
    /// Pop items with acknowledgement requirement (creates a lock).
    /// </summary>
    public async Task<PopWithAckResponse> PopWithAck(PopWithAckRequest request)
    {
        try
        {
            // Get TTL (default 30, clamped to 1-300)
            int ttlSeconds = Math.Max(MinLockTtlSeconds, Math.Min(MaxLockTtlSeconds, request.TtlSeconds));

            // Check if already locked
            var lockState = await StateManager.TryGetStateAsync<Dictionary<string, object>>("_active_lock");
            if (lockState.HasValue)
            {
                var existingLock = lockState.Value;
                double expiresAt = Convert.ToDouble(existingLock["expires_at"]);
                double now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

                if (now < expiresAt)
                {
                    return new PopWithAckResponse
                    {
                        ItemsJson = new List<string>(),
                        Count = 0,
                        Locked = true,
                        LockExpiresAt = expiresAt,
                        Message = "Queue is locked by another operation"
                    };
                }
                else
                {
                    // Expired lock - return items first
                    await HandleExpiredLockAsync(existingLock);
                }
            }

            // Pop items (just one for now, matching Python behavior)
            var popResult = await Pop();

            if (popResult.ItemsJson.Count == 0)
            {
                return new PopWithAckResponse
                {
                    ItemsJson = new List<string>(),
                    Count = 0,
                    Locked = false,
                    Message = "Queue is empty"
                };
            }

            // Create lock
            string lockId = GenerateLockId();
            double nowUnix = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            double lockExpiresAt = nowUnix + ttlSeconds;

            var lockData = new Dictionary<string, object>
            {
                ["lock_id"] = lockId,
                ["created_at"] = nowUnix,
                ["expires_at"] = lockExpiresAt,
                ["items_json"] = popResult.ItemsJson,
                ["count"] = popResult.ItemsJson.Count
            };

            await StateManager.SetStateAsync("_active_lock", lockData);
            await StateManager.SaveStateAsync();

            Logger.LogInformation($"Created lock {lockId} with TTL {ttlSeconds}s, expires at {lockExpiresAt}");

            return new PopWithAckResponse
            {
                ItemsJson = popResult.ItemsJson,
                Count = popResult.ItemsJson.Count,
                Locked = true,
                LockId = lockId,
                LockExpiresAt = lockExpiresAt,
                Message = $"Items locked with ID {lockId}"
            };
        }
        catch (Exception ex)
        {
            Logger.LogError(ex, "Error in PopWithAckAsync");
            return new PopWithAckResponse
            {
                ItemsJson = new List<string>(),
                Count = 0,
                Locked = false,
                Message = $"Error: {ex.Message}"
            };
        }
    }

    /// <summary>
    /// Acknowledge popped items using lock ID.
    /// </summary>
    public async Task<AcknowledgeResponse> Acknowledge(AcknowledgeRequest request)
    {
        try
        {
            // Validate lock_id
            if (string.IsNullOrEmpty(request.LockId))
            {
                return new AcknowledgeResponse
                {
                    Success = false,
                    Message = "lock_id cannot be empty",
                    ErrorCode = "INVALID_LOCK_ID"
                };
            }

            string lockId = request.LockId;

            // Get lock state
            var lockState = await StateManager.TryGetStateAsync<Dictionary<string, object>>("_active_lock");
            if (!lockState.HasValue)
            {
                return new AcknowledgeResponse
                {
                    Success = false,
                    Message = "Lock not found",
                    ErrorCode = "LOCK_NOT_FOUND"
                };
            }

            var lockData = lockState.Value;
            string storedLockId = lockData["lock_id"] as string ?? string.Empty;

            // Validate lock ID matches
            if (storedLockId != lockId)
            {
                return new AcknowledgeResponse
                {
                    Success = false,
                    Message = "Invalid lock_id",
                    ErrorCode = "INVALID_LOCK_ID"
                };
            }

            // Check if lock expired
            double expiresAt = Convert.ToDouble(lockData["expires_at"]);
            double now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

            if (now >= expiresAt)
            {
                // Lock expired - return items to queue
                await HandleExpiredLockAsync(lockData);

                return new AcknowledgeResponse
                {
                    Success = false,
                    Message = "Lock has expired",
                    ErrorCode = "LOCK_EXPIRED"
                };
            }

            // Acknowledge - items already removed from queue during PopWithAck
            int itemsCount = Convert.ToInt32(lockData["count"]);

            await StateManager.RemoveStateAsync("_active_lock");
            await StateManager.SaveStateAsync();

            Logger.LogInformation($"Acknowledged lock {lockId}, {itemsCount} items processed");

            return new AcknowledgeResponse
            {
                Success = true,
                Message = $"Successfully acknowledged {itemsCount} item(s)",
                ItemsAcknowledged = itemsCount
            };
        }
        catch (Exception ex)
        {
            Logger.LogError(ex, "Error in AcknowledgeAsync");
            return new AcknowledgeResponse
            {
                Success = false,
                Message = $"Error: {ex.Message}",
                ErrorCode = "INTERNAL_ERROR"
            };
        }
    }

    /// <summary>
    /// Generate a cryptographically secure 11-character alphanumeric lock ID.
    /// </summary>
    private string GenerateLockId()
    {
        // Generate 11-character alphanumeric string matching Python's secrets.token_urlsafe(8)
        const string chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
        var bytes = new byte[LockIdLength];
        using (var rng = RandomNumberGenerator.Create())
        {
            rng.GetBytes(bytes);
        }

        var result = new StringBuilder(LockIdLength);
        foreach (var b in bytes)
        {
            result.Append(chars[b % chars.Length]);
        }

        return result.ToString();
    }

    /// <summary>
    /// Helper to convert object to int, handling both regular types and JsonElement.
    /// </summary>
    private static int GetIntValue(object value)
    {
        if (value is JsonElement jsonElement)
        {
            return jsonElement.GetInt32();
        }
        return Convert.ToInt32(value);
    }
}
