using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Dapr.Actors;
using Dapr.Actors.Runtime;
using Dapr.Client;
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

            // Check and offload segments if eligible
            await CheckAndOffloadSegmentsAsync(priority, metadata);

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
                // Load any offloaded segments that are needed
                await CheckAndLoadSegmentsAsync(priority, metadata);

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
            ["config"] = new Dictionary<string, object>
            {
                ["segment_size"] = MaxSegmentSize,
                ["buffer_segments"] = 1
            },
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

    /// <summary>
    /// Helper to convert object to Dictionary, handling JsonElement deserialization.
    /// </summary>
    private static Dictionary<string, object> GetDictValue(object obj)
    {
        if (obj is JsonElement jsonElement)
        {
            return JsonSerializer.Deserialize<Dictionary<string, object>>(jsonElement.GetRawText())
                ?? new Dictionary<string, object>();
        }
        return obj as Dictionary<string, object> ?? new Dictionary<string, object>();
    }

    /// <summary>
    /// Get configured buffer_segments value (default 1).
    /// </summary>
    private int GetBufferSegments(Dictionary<string, object> metadata)
    {
        if (metadata.ContainsKey("config"))
        {
            var config = GetDictValue(metadata["config"]);
            if (config.ContainsKey("buffer_segments"))
            {
                return GetIntValue(config["buffer_segments"]);
            }
        }
        return 1; // Default buffer_segments
    }

    /// <summary>
    /// Generate state store key for offloaded segment.
    /// Format: offloaded_queue_{priority}_seg_{segmentNum}_{actorId}
    /// </summary>
    private string GetOffloadedSegmentKey(int priority, int segmentNum)
    {
        return $"offloaded_queue_{priority}_seg_{segmentNum}_{Id.GetId()}";
    }

    /// <summary>
    /// Get offloaded segment range for a priority queue.
    /// Returns (head, tail) or (null, null) if no offloaded segments exist.
    /// </summary>
    private (int? head, int? tail) GetOffloadedRange(Dictionary<string, object> metadata, int priority)
    {
        if (!metadata.ContainsKey("queues"))
            return (null, null);

        var queues = GetDictValue(metadata["queues"]);
        string priorityKey = priority.ToString();

        if (!queues.ContainsKey(priorityKey))
            return (null, null);

        var queueMeta = GetDictValue(queues[priorityKey]);

        if (queueMeta.ContainsKey("head_offloaded_segment") && queueMeta.ContainsKey("tail_offloaded_segment"))
        {
            int head = GetIntValue(queueMeta["head_offloaded_segment"]);
            int tail = GetIntValue(queueMeta["tail_offloaded_segment"]);
            return (head, tail);
        }

        return (null, null);
    }

    /// <summary>
    /// Add a segment to the offloaded range (extends tail).
    /// </summary>
    private void AddOffloadedSegment(Dictionary<string, object> metadata, int priority, int segmentNum)
    {
        if (!metadata.ContainsKey("queues"))
        {
            metadata["queues"] = new Dictionary<string, object>();
        }

        var queues = GetDictValue(metadata["queues"]);
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

        var queueMeta = GetDictValue(queues[priorityKey]);

        // If no offloaded range exists, initialize both head and tail
        if (!queueMeta.ContainsKey("head_offloaded_segment"))
        {
            queueMeta["head_offloaded_segment"] = segmentNum;
            queueMeta["tail_offloaded_segment"] = segmentNum;
        }
        else
        {
            // Extend tail (segments added sequentially)
            queueMeta["tail_offloaded_segment"] = segmentNum;
        }

        queues[priorityKey] = queueMeta;
        metadata["queues"] = queues;
    }

    /// <summary>
    /// Remove a segment from the offloaded range (shrinks from head).
    /// </summary>
    private void RemoveOffloadedSegment(Dictionary<string, object> metadata, int priority, int segmentNum)
    {
        if (!metadata.ContainsKey("queues"))
            return;

        var queues = GetDictValue(metadata["queues"]);
        string priorityKey = priority.ToString();

        if (!queues.ContainsKey(priorityKey))
            return;

        var queueMeta = GetDictValue(queues[priorityKey]);

        if (!queueMeta.ContainsKey("head_offloaded_segment") || !queueMeta.ContainsKey("tail_offloaded_segment"))
            return;

        int head = GetIntValue(queueMeta["head_offloaded_segment"]);
        int tail = GetIntValue(queueMeta["tail_offloaded_segment"]);

        // Should only remove from head (FIFO)
        if (segmentNum == head)
        {
            if (head == tail)
            {
                // Last segment in range, clear both
                queueMeta.Remove("head_offloaded_segment");
                queueMeta.Remove("tail_offloaded_segment");
            }
            else
            {
                // Move head forward
                queueMeta["head_offloaded_segment"] = head + 1;
            }

            queues[priorityKey] = queueMeta;
            metadata["queues"] = queues;
        }
    }

    /// <summary>
    /// Offload a full segment to the external state store.
    /// Returns true if successful, false otherwise (logs warning, doesn't throw).
    /// </summary>
    private async Task<bool> OffloadSegmentAsync(int priority, int segmentNum, List<Dictionary<string, object>> segmentData, Dictionary<string, object> metadata)
    {
        try
        {
            string offloadKey = GetOffloadedSegmentKey(priority, segmentNum);

            // Serialize segment data to JSON
            string segmentJson = JsonSerializer.Serialize(segmentData);

            // Save to state store using DaprClient
            using var client = new DaprClientBuilder().Build();
            await client.SaveStateAsync("statestore", offloadKey, segmentJson);

            // Add to offloaded range in metadata
            AddOffloadedSegment(metadata, priority, segmentNum);

            // Delete from actor state manager
            string segmentKey = $"queue_{priority}_seg_{segmentNum}";
            await StateManager.RemoveStateAsync(segmentKey);

            // Save metadata
            await SaveMetadataAsync(metadata);
            await StateManager.SaveStateAsync();

            Logger.LogDebug($"Offloaded segment {segmentNum} for priority {priority} (actor {Id.GetId()})");
            return true;
        }
        catch (Exception ex)
        {
            Logger.LogWarning(ex, $"Failed to offload segment {segmentNum} for priority {priority} (actor {Id.GetId()})");
            return false;
        }
    }

    /// <summary>
    /// Load an offloaded segment from state store back into actor state.
    /// Returns segment data if successful, null otherwise (logs error).
    /// </summary>
    private async Task<List<Dictionary<string, object>>?> LoadOffloadedSegmentAsync(int priority, int segmentNum, Dictionary<string, object> metadata)
    {
        try
        {
            string offloadKey = GetOffloadedSegmentKey(priority, segmentNum);

            // Load from state store
            using var client = new DaprClientBuilder().Build();
            var result = await client.GetStateAsync<string>("statestore", offloadKey);

            if (string.IsNullOrEmpty(result))
            {
                Logger.LogWarning($"No data found for offloaded segment {segmentNum} priority {priority} (actor {Id.GetId()})");
                return null;
            }

            // Deserialize from JSON
            var segmentData = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(result);

            if (segmentData == null || segmentData.Count == 0)
            {
                Logger.LogWarning($"Empty data for offloaded segment {segmentNum} priority {priority} (actor {Id.GetId()})");
                return null;
            }

            // Save to actor state manager
            string segmentKey = $"queue_{priority}_seg_{segmentNum}";
            await StateManager.SetStateAsync(segmentKey, segmentData);

            // Remove from offloaded range
            RemoveOffloadedSegment(metadata, priority, segmentNum);

            // Delete from state store
            await client.DeleteStateAsync("statestore", offloadKey);

            // Save metadata
            await SaveMetadataAsync(metadata);
            await StateManager.SaveStateAsync();

            Logger.LogDebug($"Loaded segment {segmentNum} for priority {priority} from state store (actor {Id.GetId()})");
            return segmentData;
        }
        catch (Exception ex)
        {
            Logger.LogError(ex, $"Failed to load offloaded segment {segmentNum} for priority {priority} (actor {Id.GetId()})");
            return null;
        }
    }

    /// <summary>
    /// Check and offload eligible segments for a priority queue.
    /// Called after Push. Non-blocking - failures are logged but don't throw.
    /// </summary>
    private async Task CheckAndOffloadSegmentsAsync(int priority, Dictionary<string, object> metadata)
    {
        try
        {
            if (!metadata.ContainsKey("queues"))
                return;

            var queues = GetDictValue(metadata["queues"]);
            string priorityKey = priority.ToString();

            if (!queues.ContainsKey(priorityKey))
                return;

            var queueMeta = GetDictValue(queues[priorityKey]);

            int headSegment = GetIntValue(queueMeta["head_segment"]);
            int tailSegment = GetIntValue(queueMeta["tail_segment"]);
            int bufferSegments = GetBufferSegments(metadata);
            var offloadedRange = GetOffloadedRange(metadata, priority);

            // Calculate eligible segment range
            int minOffload = headSegment + bufferSegments + 1;
            int maxOffload = tailSegment;

            // Check each segment in range
            for (int segmentNum = minOffload; segmentNum < maxOffload; segmentNum++)
            {
                // Skip if already offloaded
                if (offloadedRange.head != null && offloadedRange.tail != null)
                {
                    if (segmentNum >= offloadedRange.head && segmentNum <= offloadedRange.tail)
                        continue;
                }

                // Check if segment exists and is full
                string segmentKey = $"queue_{priority}_seg_{segmentNum}";
                var segment = await StateManager.TryGetStateAsync<List<Dictionary<string, object>>>(segmentKey);

                if (segment.HasValue && segment.Value.Count == MaxSegmentSize)
                {
                    // Offload this segment (non-blocking on failure)
                    await OffloadSegmentAsync(priority, segmentNum, segment.Value, metadata);
                }
            }
        }
        catch (Exception ex)
        {
            Logger.LogWarning(ex, $"Error checking/offloading segments for priority {priority} (actor {Id.GetId()})");
        }
    }

    /// <summary>
    /// Check and load offloaded segments that are needed for consumption.
    /// Called before Pop. Blocking - throws exceptions on failure to prevent data corruption.
    /// </summary>
    private async Task CheckAndLoadSegmentsAsync(int priority, Dictionary<string, object> metadata)
    {
        var offloadedRange = GetOffloadedRange(metadata, priority);
        if (offloadedRange.head == null || offloadedRange.tail == null)
            return;

        if (!metadata.ContainsKey("queues"))
            return;

        var queues = GetDictValue(metadata["queues"]);
        string priorityKey = priority.ToString();

        if (!queues.ContainsKey(priorityKey))
            return;

        var queueMeta = GetDictValue(queues[priorityKey]);

        int headSegment = GetIntValue(queueMeta["head_segment"]);
        int bufferSegments = GetBufferSegments(metadata);

        // Calculate which segments should be loaded
        int maxOffloaded = headSegment + bufferSegments;

        // Load segments that are within the buffer zone (from head of offloaded range)
        for (int segmentNum = offloadedRange.head.Value; segmentNum <= offloadedRange.tail.Value; segmentNum++)
        {
            if (segmentNum <= maxOffloaded)
            {
                await LoadOffloadedSegmentAsync(priority, segmentNum, metadata);
            }
            else
            {
                // Since segments are contiguous, we can break early
                break;
            }
        }
    }
}
