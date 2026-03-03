using System.Text.Json;
using Dapr.Actors;
using Dapr.Actors.Client;
using Microsoft.AspNetCore.Mvc;
using PushPopActor.Interfaces;
using PushPopActor.ApiServer.Constants;
using PushPopActor.ApiServer.Models;

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
                return BadRequest(new ApiErrorResponse("Priority must be non-negative"));
            }

            _logger.LogDebug($"Push request for queue {queueId} with priority {request.Priority}");

            var actorId = new ActorId(queueId);
            var proxy = ActorProxy.Create(actorId, "PushPopActor");

            // Get raw JSON string from JsonElement (no unnecessary deserialization)
            var itemJson = request.Item.GetRawText();

            var result = await proxy.InvokeMethodAsync<PushRequest, PushResponse>(
                ActorMethodNames.Push,
                new PushRequest
                {
                    ItemJson = itemJson,
                    Priority = request.Priority
                });

            if (result.Success)
            {
                return Ok(new ApiPushResponse(
                    true,
                    $"Item pushed to queue {queueId} at priority {request.Priority}"
                ));
            }

            return BadRequest(new ApiErrorResponse("Failed to push item"));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error pushing item to queue {queueId}");
            return StatusCode(500, new ApiErrorResponse($"Internal error: {ex.Message}"));
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
            var proxy = ActorProxy.Create(actorId, "PushPopActor");

            if (require_ack)
            {
                var result = await proxy.InvokeMethodAsync<PopWithAckRequest, PopWithAckResponse>(
                    ActorMethodNames.PopWithAck,
                    new PopWithAckRequest
                    {
                        TtlSeconds = ttl_seconds
                    });

                // If locked by another operation, return 423 Locked
                if (result.Locked && result.ItemJson == null)
                {
                    return StatusCode(423, new ApiLockedResponse(
                        result.Message,
                        result.LockExpiresAt
                    ));
                }

                // Parse JSON string to JsonElement for API response (no unnecessary deserialization)
                object? item = null;
                if (result.ItemJson != null)
                {
                    item = JsonDocument.Parse(result.ItemJson).RootElement;
                }

                return Ok(new ApiPopWithAckResponse(
                    item,
                    result.Locked,
                    result.LockId,
                    result.LockExpiresAt,
                    result.Message
                ));
            }
            else
            {
                var result = await proxy.InvokeMethodAsync<PopResponse>(ActorMethodNames.Pop);

                // Parse JSON string to JsonElement for API response (no unnecessary deserialization)
                object? item = null;
                if (result.ItemJson != null)
                {
                    item = JsonDocument.Parse(result.ItemJson).RootElement;
                }

                return Ok(new ApiPopResponse(item));
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error popping item from queue {queueId}");
            return StatusCode(500, new ApiErrorResponse($"Internal error: {ex.Message}"));
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
            var proxy = ActorProxy.Create(actorId, "PushPopActor");

            var result = await proxy.InvokeMethodAsync<AcknowledgeRequest, AcknowledgeResponse>(
                ActorMethodNames.Acknowledge,
                new AcknowledgeRequest
                {
                    LockId = request.LockId
                });

            // Check for error codes
            if (!result.Success)
            {
                var response = new ApiAcknowledgeResponse(
                    result.Success,
                    result.Message,
                    ErrorCode: result.ErrorCode
                );

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

            return Ok(new ApiAcknowledgeResponse(
                result.Success,
                result.Message,
                result.ItemsAcknowledged
            ));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error acknowledging items for queue {queueId}");
            return StatusCode(500, new ApiErrorResponse($"Internal error: {ex.Message}"));
        }
    }
}
