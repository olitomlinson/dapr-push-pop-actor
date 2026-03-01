using System.Text.Json;
using Dapr.Actors;
using Dapr.Actors.Client;
using Microsoft.AspNetCore.Mvc;
using PushPopActor.Interfaces;

namespace PushPopActor.ApiServer.Controllers;

[ApiController]
[Route("queue")]
public class QueueController : ControllerBase
{
    private readonly ILogger<QueueController> _logger;

    public QueueController(ILogger<QueueController> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Push an item to the queue with optional priority.
    /// </summary>
    [HttpPost("{queueId}/push")]
    public async Task<IActionResult> Push(
        string queueId,
        [FromBody] ApiPushRequest request)
    {
        try
        {
            if (request.Priority < 0)
            {
                return BadRequest(new { success = false, message = "Priority must be non-negative" });
            }

            _logger.LogDebug($"Push request for queue {queueId} with priority {request.Priority}");

            var actorId = new ActorId(queueId);
            var proxy = ActorProxy.Create<IPushPopActor>(actorId, "PushPopActor");

            // Serialize the item dictionary to JSON string for the actor
            var itemJson = JsonSerializer.Serialize(request.Item);

            var result = await proxy.Push(new PushRequest
            {
                ItemJson = itemJson,
                Priority = request.Priority
            });

            if (result.Success)
            {
                return Ok(new
                {
                    success = true,
                    message = $"Item pushed to queue {queueId} at priority {request.Priority}"
                });
            }

            return BadRequest(new { success = false, message = "Failed to push item" });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error pushing item to queue {queueId}");
            return StatusCode(500, new { success = false, message = $"Internal error: {ex.Message}" });
        }
    }

    /// <summary>
    /// Pop items from the queue with optional acknowledgement.
    /// </summary>
    [HttpPost("{queueId}/pop")]
    public async Task<IActionResult> Pop(
        string queueId,
        [FromQuery] bool require_ack = false,
        [FromQuery] int ttl_seconds = 30)
    {
        try
        {
            _logger.LogDebug($"Pop request for queue {queueId}, require_ack={require_ack}");

            var actorId = new ActorId(queueId);
            var proxy = ActorProxy.Create<IPushPopActor>(actorId, "PushPopActor");

            if (require_ack)
            {
                var result = await proxy.PopWithAck(new PopWithAckRequest
                {
                    TtlSeconds = ttl_seconds
                });

                // If locked by another operation, return 423 Locked
                if (result.Locked && result.Count == 0)
                {
                    return StatusCode(423, new
                    {
                        message = result.Message,
                        lock_expires_at = result.LockExpiresAt
                    });
                }

                // Deserialize JSON strings back to objects for API response
                var items = result.ItemsJson
                    .Select(json => JsonSerializer.Deserialize<Dictionary<string, object>>(json))
                    .ToList();

                return Ok(new
                {
                    items,
                    count = result.Count,
                    locked = result.Locked,
                    lock_id = result.LockId,
                    lock_expires_at = result.LockExpiresAt,
                    message = result.Message
                });
            }
            else
            {
                var result = await proxy.Pop();

                // Deserialize JSON string back to object for API response
                object? item = null;
                if (result.ItemsJson.Count > 0)
                {
                    item = JsonSerializer.Deserialize<Dictionary<string, object>>(result.ItemsJson[0]);
                }

                return Ok(new { item });
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error popping item from queue {queueId}");
            return StatusCode(500, new { message = $"Internal error: {ex.Message}" });
        }
    }

    /// <summary>
    /// Acknowledge popped items using lock ID.
    /// </summary>
    [HttpPost("{queueId}/acknowledge")]
    public async Task<IActionResult> Acknowledge(
        string queueId,
        [FromBody] ApiAcknowledgeRequest request)
    {
        try
        {
            _logger.LogDebug($"Acknowledge request for queue {queueId} with lock_id {request.LockId}");

            var actorId = new ActorId(queueId);
            var proxy = ActorProxy.Create<IPushPopActor>(actorId, "PushPopActor");

            var result = await proxy.Acknowledge(new AcknowledgeRequest
            {
                LockId = request.LockId
            });

            // Check for error codes
            if (!result.Success)
            {
                var response = new
                {
                    success = result.Success,
                    message = result.Message,
                    error_code = result.ErrorCode
                };

                // Return 410 Gone if lock expired
                if (result.ErrorCode == "LOCK_EXPIRED")
                {
                    return StatusCode(410, response);
                }

                // Return 404 if lock not found
                if (result.ErrorCode == "LOCK_NOT_FOUND")
                {
                    return NotFound(response);
                }

                // Return 400 for invalid lock_id
                if (result.ErrorCode == "INVALID_LOCK_ID")
                {
                    return BadRequest(response);
                }

                // Default to 400 for other failures
                return BadRequest(response);
            }

            return Ok(new
            {
                success = result.Success,
                message = result.Message,
                items_acknowledged = result.ItemsAcknowledged
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error acknowledging items for queue {queueId}");
            return StatusCode(500, new { message = $"Internal error: {ex.Message}" });
        }
    }
}

// Request/Response models for API endpoints
public record ApiPushRequest(
    Dictionary<string, object> Item,
    int Priority = 0
);

public record ApiAcknowledgeRequest(
    string LockId
);
